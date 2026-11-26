from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from src.core.human_labels import format_metric_for_summary, humanize_label
from src.repositories.statistics_repository import DatasetUnavailableError, StatisticsRepository
from src.schemas.ai_search import AISearchResponse, AISearchRoutingPlan, AllowedColumn, DatasetId
from src.services.gemini_client import ExternalAIServiceError, RoutingLLMClientProtocol
from src.services.query_cache import AIQueryCache

logger = logging.getLogger(__name__)

OUT_OF_DOMAIN_MESSAGE = (
    "Esa información no se encuentra disponible en este portal estadístico. "
    "Puedes consultar indicadores oficiales agregados sobre los temas publicados en el sistema "
    "(demografía, migración de retorno, costo de vida, educación superior, seguridad vial e índices de vulnerabilidad)."
)

PRIVACY_BLOCK_MESSAGE = (
    "Este portal únicamente procesa y publica estadísticas poblacionales agregadas y anónimas. "
    "Por políticas de privacidad y protección de datos personales, no se realizan búsquedas sobre personas individuales."
)

EMPTY_RESULTS_MESSAGE = "No se encontraron registros estadísticos para los criterios consultados."

DEFAULT_SUCCESS_MESSAGE = "Se presentan las estadísticas oficiales agregadas correspondientes a su consulta."

_PII_IDENTIFIER_RE = re.compile(
    r"\b("
    r"dpi|cui|nit|pasaporte|numero\s+de\s+telefono|celular\s+de|correo\s+electronico\s+de|"
    r"direccion\s+exacta|domicilio\s+de|donde\s+vive|antecedentes\s+de|expediente\s+de|"
    r"partida\s+de\s+nacimiento\s+de|acta\s+de\s+defuncion\s+de"
    r")\b",
    re.IGNORECASE,
)
_CUI_DIGITS_RE = re.compile(r"\b\d{4}\s?\d{5}\s?\d{4}\b")
_HONORIFIC_PERSON_RE = re.compile(
    r"\b(senor|señor|senora|señora|sr\.|sra\.|don|dona|doña|ciudadano|ciudadana|individuo)\s+[a-záéíóúñ]{2,}",
    re.IGNORECASE,
)

_FORBIDDEN_LEAK_TERMS_RE = re.compile(
    r"(\.parquet|polars|duckdb|dataframe|scan_parquet|traceback|sql|data/processed|data/raw)",
    re.IGNORECASE,
)

# Mapa determinista de respaldo para recuperar la parte disponible en consultas mixtas/parciales
_AVAILABLE_DOMAIN_RECOVERY: Tuple[Tuple[re.Pattern[str], DatasetId, List[AllowedColumn]], ...] = (
    (
        re.compile(r"\b(migraci[oó]n|migrantes?|retornados?|retorno)\b", re.IGNORECASE),
        "indicadores_departamentales",
        ["tasa_retorno_migratorio_por_10k", "retornados_total"],
    ),
    (
        re.compile(r"\b(universidad|educaci[oó]n\s+superior|matr[ií]cula)\b", re.IGNORECASE),
        "indicadores_departamentales",
        ["tasa_matricula_superior_por_10k", "matriculados_superior_total", "pct_mujeres_superior"],
    ),
    (
        re.compile(r"\b(natalidad|nacimientos?)\b", re.IGNORECASE),
        "indicadores_departamentales",
        ["tasa_natalidad_por_1000", "nacimientos_total"],
    ),
    (
        re.compile(r"\b(mortalidad|defunciones?)\b", re.IGNORECASE),
        "indicadores_departamentales",
        ["tasa_mortalidad_por_1000", "defunciones_total"],
    ),
    (
        re.compile(r"\b(accidentes?|tr[aá]nsito|vial|viales|siniestros?)\b", re.IGNORECASE),
        "indicadores_departamentales",
        ["tasa_victimas_viales_por_100k", "victimas_viales_total"],
    ),
    (
        re.compile(r"\b(necropsias?|inacif|forense)\b", re.IGNORECASE),
        "indicadores_departamentales",
        ["tasa_necropsias_por_100k", "necropsias_total"],
    ),
    (
        re.compile(r"\b(inflaci[oó]n|ipc|precios)\b", re.IGNORECASE),
        "indicadores_departamentales",
        ["inflacion_regional_interanual", "indice_ipc_regional"],
    ),
    (
        re.compile(r"\b(canasta\s+b[aá]sica|costo\s+de\s+vida|cba)\b", re.IGNORECASE),
        "proyecciones_costo_vida",
        ["costo_actual_percapita", "proyeccion_12_meses_gtq"],
    ),
    (
        re.compile(r"\b(vulnerabilidad|ivst)\b", re.IGNORECASE),
        "vulnerabilidad_departamental",
        ["indice_vulnerabilidad_ivst", "nivel_vulnerabilidad"],
    ),
    (
        re.compile(r"\b(poblaci[oó]n|habitantes|demograf[ií]a)\b", re.IGNORECASE),
        "indicadores_departamentales",
        ["poblacion_total", "razon_dependencia_demografica"],
    ),
)

_POVERTY_TOPIC_RE = re.compile(r"\b(pobreza|condiciones\s+de\s+vida|carencias)\b", re.IGNORECASE)

_KNOWN_ABSENT_TOPICS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(desempleo|empleo\s+informal|subempleo|fuentes?\s+de\s+trabajo)\b", re.IGNORECASE), "desempleo / mercado laboral"),
    (re.compile(r"\b(pobreza|extrema\s+pobreza)\b", re.IGNORECASE), "pobreza monetaria"),
    (re.compile(r"\b(desnutrici[oó]n|inseguridad\s+alimentaria)\b", re.IGNORECASE), "desnutrición"),
    (re.compile(r"\b(salario\s+m[ií]nimo|ingresos?\s+laborales?)\b", re.IGNORECASE), "salario e ingresos laborales"),
)

_SUMMARY_SKIP_KEYS: frozenset[str] = frozenset(
    {
        "Posición",
        "Departamento",
        "Región",
        "Código departamento",
        "Código región",
        "Código ISO",
    }
)


def is_personal_data_query(query: str) -> bool:
    """Detectar de forma determinista intentos de consultar identificadores o registros individuales."""
    if _PII_IDENTIFIER_RE.search(query):
        return True
    if _CUI_DIGITS_RE.search(query):
        return True
    if _HONORIFIC_PERSON_RE.search(query):
        return True
    return False


def sanitize_public_message(candidate: Optional[str]) -> str:
    """Garantizar que el mensaje contextual nunca filtre terminologia tecnica interna."""
    if not candidate or not candidate.strip():
        return DEFAULT_SUCCESS_MESSAGE
    cleaned = candidate.strip()
    if _FORBIDDEN_LEAK_TERMS_RE.search(cleaned) or len(cleaned) > 1200:
        return DEFAULT_SUCCESS_MESSAGE
    return cleaned


class AISearchService:
    """Servicio orquestador de busqueda estadistica inteligente (SRP + Privacidad por Diseno)."""

    def __init__(
        self,
        llm_client: RoutingLLMClientProtocol,
        repository: StatisticsRepository,
        cache: AIQueryCache,
    ) -> None:
        self._llm_client = llm_client
        self._repository = repository
        self._cache = cache

    def search(self, sanitized_query: str) -> AISearchResponse:
        # 1. Bloqueo determinista temprano de privacidad (antes de consumir cuota del LLM)
        if is_personal_data_query(sanitized_query):
            return AISearchResponse(
                mensaje=PRIVACY_BLOCK_MESSAGE,
                datos=[],
                visualizacion_url=None,
            )

        # 2. Descubrir conjuntos adicionales procesados localmente (Explorar datos)
        dynamic_datasets = self._repository.list_dynamic_datasets()
        dynamic_signature = ",".join(f"{d.slug}:{d.stem}" for d in dynamic_datasets)
        cache_key = f"{sanitized_query}||{dynamic_signature}" if dynamic_signature else sanitized_query

        cached_response = self._cache.get(cache_key)
        if cached_response is not None:
            return cached_response

        dynamic_context = self._format_dynamic_context(dynamic_datasets)

        # 3. Traduccion estructurada Text-to-JSON mediante Gemini
        if dynamic_context:
            try:
                plan: AISearchRoutingPlan = self._llm_client.build_routing_plan(sanitized_query, dynamic_context)
            except TypeError:
                plan = self._llm_client.build_routing_plan(sanitized_query)
        else:
            plan = self._llm_client.build_routing_plan(sanitized_query)

        # 4. Evaluacion de bloqueo de privacidad
        if plan.tipo_intencion == "bloqueo_privacidad":
            response = AISearchResponse(
                mensaje=PRIVACY_BLOCK_MESSAGE,
                datos=[],
                visualizacion_url=None,
            )
            self._cache.set(cache_key, response)
            return response

        # 4b. Recuperacion inteligente si un tema no existe pero otro de la misma pregunta SI existe en .parquet
        plan = self._recover_partial_plan_if_applicable(sanitized_query, plan)

        has_fixed_dataset = plan.conjunto_datos is not None
        has_dynamic_dataset = bool(plan.conjunto_dinamico_slug)

        if plan.tipo_intencion == "fuera_de_dominio" or (not has_fixed_dataset and not has_dynamic_dataset):
            missing_topic = (plan.indicador_no_disponible or "").strip()
            if (
                missing_topic
                and len(missing_topic) <= 60
                and not _FORBIDDEN_LEAK_TERMS_RE.search(missing_topic)
            ):
                msg_out = (
                    f"El indicador o tema «{missing_topic}» no forma parte de los conjuntos procesados actualmente en este portal, "
                    "por lo que no se emiten estimaciones sin respaldo oficial. "
                    "Puedes consultar indicadores disponibles sobre demografía, migración de retorno, "
                    "costo de vida, educación superior, seguridad vial e índices de vulnerabilidad."
                )
            else:
                msg_out = OUT_OF_DOMAIN_MESSAGE

            response = AISearchResponse(
                mensaje=msg_out,
                datos=[],
                visualizacion_url=None,
            )
            self._cache.set(cache_key, response)
            return response

        # 5. Ejecucion en modo solo lectura segun subtipo de consulta
        total_dynamic_records: Optional[int] = None
        bivariate_summary: Optional[str] = None

        is_bivariate = has_fixed_dataset and (
            plan.subtipo_consulta == "relacion_bivariada"
            or (
                plan.conjunto_datos == "matriz_correlaciones"
                and len(
                    [
                        c
                        for c in plan.columnas_metricas
                        if c not in {"pearson_r", "pearson_pvalue", "spearman_rho", "fuerza_asociacion", "variable_1", "variable_2"}
                    ]
                )
                >= 2
            )
        )

        try:
            if is_bivariate:
                rows, vis_url, bivariate_summary = self._repository.execute_bivariate_analysis(plan)
            elif has_fixed_dataset:
                rows, vis_url = self._repository.execute_plan(plan)
            else:
                rows, vis_url, total_dynamic_records = self._repository.execute_dynamic_plan(plan)
        except DatasetUnavailableError as exc:
            logger.error("Fuente de datos estadisticos no disponible durante consulta (%s).", type(exc).__name__)
            raise ExternalAIServiceError("Datos estadisticos temporalmente no disponibles.") from exc

        if not rows:
            response = AISearchResponse(
                mensaje=EMPTY_RESULTS_MESSAGE,
                datos=[],
                visualizacion_url=None,
            )
            self._cache.set(cache_key, response)
            return response

        final_msg = self._compose_executive_message(
            plan=plan,
            rows=rows,
            total_dynamic_records=total_dynamic_records,
            bivariate_summary=bivariate_summary,
        )

        response = AISearchResponse(
            mensaje=final_msg,
            datos=rows,
            visualizacion_url=vis_url,
        )
        self._cache.set(cache_key, response)
        return response

    @staticmethod
    def _recover_partial_plan_if_applicable(
        sanitized_query: str,
        plan: AISearchRoutingPlan,
    ) -> AISearchRoutingPlan:
        """Convertir rechazos totales o planes sin etiqueta parcial cuando coexisten un tema ausente y uno disponible."""
        inferred_absent = next(
            (label for pat, label in _KNOWN_ABSENT_TOPICS if pat.search(sanitized_query)),
            "",
        )
        missing = (plan.indicador_no_disponible or "").strip() or inferred_absent

        if plan.tipo_intencion == "consulta_estadistica":
            if missing and (plan.subtipo_consulta != "respuesta_parcial" or not plan.indicador_no_disponible):
                return plan.model_copy(
                    update={
                        "subtipo_consulta": "respuesta_parcial",
                        "indicador_no_disponible": missing,
                    }
                )
            return plan

        if plan.tipo_intencion != "fuera_de_dominio" or not missing:
            return plan

        recovered_metrics: List[AllowedColumn] = []
        primary_ds: Optional[DatasetId] = None
        for pattern, ds_id, cols in _AVAILABLE_DOMAIN_RECOVERY:
            if pattern.search(sanitized_query):
                if primary_ds is None:
                    primary_ds = ds_id
                for col in cols:
                    if col not in recovered_metrics:
                        recovered_metrics.append(col)

        if primary_ds is None or not recovered_metrics:
            return plan

        # Si el tema ausente es pobreza, complementar con IVST aclarando su definicion sin asumir equivalencia
        if _POVERTY_TOPIC_RE.search(missing) or _POVERTY_TOPIC_RE.search(sanitized_query):
            if primary_ds == "indicadores_departamentales":
                for v_col in ("indice_vulnerabilidad_ivst", "nivel_vulnerabilidad"):
                    if v_col not in recovered_metrics:
                        recovered_metrics.append(v_col)  # type: ignore[arg-type]

        return plan.model_copy(
            update={
                "tipo_intencion": "consulta_estadistica",
                "subtipo_consulta": "respuesta_parcial",
                "conjunto_datos": primary_ds,
                "columnas_metricas": recovered_metrics,
                "ordenar_por": recovered_metrics[0],
                "limite": 10,
                "visualizacion_sugerida": "ranking_departamental" if primary_ds != "proyecciones_costo_vida" else "tendencia_costo_vida",
            }
        )

    def _compose_executive_message(
        self,
        *,
        plan: AISearchRoutingPlan,
        rows: List[Dict[str, Any]],
        total_dynamic_records: Optional[int],
        bivariate_summary: Optional[str],
    ) -> str:
        base_msg = sanitize_public_message(plan.mensaje_contextual)
        partial_prefix = self._build_partial_disclaimer(plan)

        if bivariate_summary:
            return sanitize_public_message(f"{partial_prefix}{bivariate_summary}")

        if plan.subtipo_consulta == "multi_consulta" and plan.columnas_metricas:
            multi_summary = self._repository.build_multi_query_summary(
                plan.columnas_metricas,
                direccion_orden=plan.direccion_orden,
            )
            if multi_summary:
                return sanitize_public_message(f"{partial_prefix}{multi_summary}")

        if total_dynamic_records is not None:
            total_prefix = (
                f"El conjunto oficial registra un total general de {total_dynamic_records:,} registros procesados. "
            )
            return sanitize_public_message(f"{partial_prefix}{total_prefix}{base_msg}")

        pos_key = humanize_label("posicion")
        depto_key = humanize_label("depto_nombre")
        muni_key = humanize_label("mupio_codigo_str")
        mujeres_key = humanize_label("mujeres")
        hombres_key = humanize_label("hombres")

        # Resumen explicito de todas las metricas pedidas cuando se consulta un territorio puntual o Top 1..3
        if 1 <= len(rows) <= 3 and depto_key in rows[0] and muni_key not in rows[0]:
            first = rows[0]
            metric_snippets = self._extract_row_metric_snippets(first, plan)
            if len(rows) == 1 and plan.codigos_departamento and pos_key in first:
                orden_txt = "de mayor a menor" if plan.direccion_orden == "desc" else "de menor a mayor"
                rank_lead = (
                    f"{first[depto_key]} se ubica en la posición #{first[pos_key]} de 22 departamentos "
                    f"(ordenado {orden_txt})."
                )
                if metric_snippets:
                    return sanitize_public_message(
                        f"{partial_prefix}{rank_lead} Cifras oficiales registradas: {'; '.join(metric_snippets)}."
                    )
                return sanitize_public_message(f"{partial_prefix}{rank_lead} {base_msg}")

            if len(rows) == 1 and len(metric_snippets) >= 2:
                return sanitize_public_message(
                    f"{partial_prefix}{first[depto_key]} registra: {'; '.join(metric_snippets)}. {base_msg}"
                )

        if len(rows) == 22 and mujeres_key in rows[0] and hombres_key in rows[0]:
            total_m = sum(int(r.get(mujeres_key) or 0) for r in rows)
            total_h = sum(int(r.get(hombres_key) or 0) for r in rows)
            grand = max(total_m + total_h, 1)
            pct_m = (total_m / grand) * 100.0
            pct_h = (total_h / grand) * 100.0
            sex_prefix = (
                f"Total nacional proyectado: {total_m:,} mujeres ({pct_m:.1f}%) "
                f"frente a {total_h:,} hombres ({pct_h:.1f}%). "
            )
            return sanitize_public_message(f"{partial_prefix}{sex_prefix}{base_msg}")

        if partial_prefix:
            multi_lead = self._repository.build_multi_query_summary(
                plan.columnas_metricas,
                direccion_orden=plan.direccion_orden,
            )
            body_txt = multi_lead or base_msg
            return sanitize_public_message(f"{partial_prefix}{body_txt}")

        return base_msg

    @staticmethod
    def _build_partial_disclaimer(plan: AISearchRoutingPlan) -> str:
        missing = (plan.indicador_no_disponible or "").strip()
        if plan.subtipo_consulta != "respuesta_parcial" and not missing:
            return ""
        topic_txt = f"«{missing}»" if missing and not _FORBIDDEN_LEAK_TERMS_RE.search(missing) else "uno de los temas consultados"
        ivst_note = ""
        if "indice_vulnerabilidad_ivst" in plan.columnas_metricas or "nivel_vulnerabilidad" in plan.columnas_metricas:
            ivst_note = (
                " Como referencia territorial complementaria (no equivalente a pobreza monetaria), se incluye el "
                "Índice de Vulnerabilidad Socioeconómica Territorial (IVST), que resume presión demográfica, retorno migratorio, matrícula e inflación regional."
            )
        return (
            f"Nota de alcance: este portal no cuenta con series procesadas sobre {topic_txt}, "
            f"por lo que no se inventan cifras ni se asumen equivalencias; sí se entregan los datos oficiales disponibles.{ivst_note} "
        )

    @staticmethod
    def _extract_row_metric_snippets(row: Dict[str, Any], plan: AISearchRoutingPlan) -> List[str]:
        requested_labels = [humanize_label(c) for c in plan.columnas_metricas]
        keys_to_show = [k for k in requested_labels if k in row and k not in _SUMMARY_SKIP_KEYS]
        if not keys_to_show:
            keys_to_show = [k for k in row.keys() if k not in _SUMMARY_SKIP_KEYS]

        reverse_map = {humanize_label(c): c for c in plan.columnas_metricas}
        snippets: List[str] = []
        for pub_key in keys_to_show[:6]:
            raw_col = reverse_map.get(pub_key, pub_key)
            val_str = format_metric_for_summary(raw_col, row[pub_key])
            snippets.append(f"{pub_key}: {val_str}")
        return snippets

    @staticmethod
    def _format_dynamic_context(dynamic_datasets: list) -> str:
        if not dynamic_datasets:
            return ""
        lines = ["CONJUNTOS ADICIONALES PROCESADOS EN CATÁLOGO LOCAL:"]
        for info in dynamic_datasets:
            cols_preview = ", ".join(info.groupable_columns[:14])
            lines.append(
                f"- conjunto_dinamico_slug=\"{info.slug}\" | conjunto_dinamico_archivo=\"{info.stem}\" "
                f"| columnas_agrupables=[{cols_preview}]"
            )
        return "\n".join(lines)
