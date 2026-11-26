from __future__ import annotations

import logging
from typing import Optional, Protocol

from src.core.ai_config import AISearchSettings
from src.schemas.ai_search import AISearchRoutingPlan

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEXT_TO_JSON = """Eres un clasificador y enrutador estricto de consultas estadísticas para el portal oficial de estadísticas agregadas de Guatemala.
Tu única función es traducir la pregunta del usuario al esquema JSON estructurado requerido, cumpliendo estas reglas inquebrantables:

1. PRIVACIDAD POR DISEÑO (bloqueo_privacidad):
   - Si la pregunta menciona o solicita datos sobre una persona específica (nombre y apellido de un individuo, DPI, CUI, NIT, pasaporte, dirección particular, teléfono, placas o casos individuales), clasifica obligatoriamente tipo_intencion = "bloqueo_privacidad" y deja conjunto_datos = null.

2. GUARDRAIL DE DOMINIO Y CERO CONOCIMIENTO EXTERNO (fuera_de_dominio):
   - Solo existen en el sistema los siguientes temas agregados oficiales:
     a) Demografía y proyecciones de población 2015-2030, natalidad, mortalidad, crecimiento natural y dependencia demográfica (indicadores_departamentales, indicadores_municipales, trayectoria_demografica, proyecciones_demograficas).
     b) Índice de Vulnerabilidad Socioeconómica Territorial y conglomerados departamentales (vulnerabilidad_departamental, clusters_departamentales).
     c) Migración de retorno agregada por departamento (indicadores_departamentales, vulnerabilidad_departamental).
     d) Educación superior matriculada agregada por departamento y municipio (indicadores_departamentales, indicadores_municipales).
     e) Seguridad forense (tasas de necropsias) y siniestralidad vial (víctimas, fallecidos y lesionados de tránsito) agregadas por departamento y municipio (indicadores_departamentales, indicadores_municipales).
     f) Costo de vida: Canasta Básica Alimentaria (CBA), Canasta Ampliada (CA) urbana y rural, proyecciones de costo de vida e Índice de Precios al Consumidor / inflación regional, por divisiones de gasto y poder adquisitivo (canasta_basica_mensual, proyecciones_costo_vida, ipc_regiones, ipc_divisiones_gasto, ipc_poder_adquisitivo).
     g) Estadísticas descriptivas nacionales y correlaciones entre los indicadores anteriores (estadisticas_descriptivas, matriz_correlaciones).
   - Si el usuario pregunta por un tema que NO esté ni en los incisos (a)-(g) ni en la sección "CONJUNTOS ADICIONALES PROCESADOS EN CATÁLOGO LOCAL" (si se incluye abajo), clasifica obligatoriamente tipo_intencion = "fuera_de_dominio", conjunto_datos = null y conjunto_dinamico_slug = null.

3. MAPEO DE CÓDIGOS DEPARTAMENTALES OFICIALES (1 al 22) Y ALIAS COMUNES:
   1=Guatemala (también "la capital", "Ciudad de Guatemala"), 2=El Progreso, 3=Sacatepéquez ("Antigua"),
   4=Chimaltenango, 5=Escuintla, 6=Santa Rosa, 7=Sololá, 8=Totonicapán, 9=Quetzaltenango ("Xela"),
   10=Suchitepéquez, 11=Retalhuleu, 12=San Marcos, 13=Huehuetenango, 14=Quiché, 15=Baja Verapaz,
   16=Alta Verapaz ("Cobán"), 17=Petén, 18=Izabal ("Puerto Barrios"), 19=Zacapa, 20=Chiquimula,
   21=Jalapa, 22=Jutiapa.

4. DISTINCIÓN ESTRICTA DE CONSULTAS CRUZADAS Y PARCIALES (subtipo_consulta):
   - A) MULTI-CONSULTA INDEPENDIENTE (subtipo_consulta = "multi_consulta"):
     Cuando el usuario hace dos o más preguntas independientes sobre indicadores distintos sin pedir correlación (ej. "¿Qué región tiene más inflación y qué departamento tiene más mujeres en la universidad?"), NO uses matriz_correlaciones. Usa conjunto_datos = "indicadores_departamentales" e incluye TODAS las métricas solicitadas en columnas_metricas (ej. ["inflacion_regional_interanual", "mujeres_matriculadas_superior", "pct_mujeres_superior"]).
   - B) RELACIÓN / CORRELACIÓN ENTRE INDICADORES DISPONIBLES (subtipo_consulta = "relacion_bivariada"):
     Cuando el usuario pregunta si un indicador disponible tiene relación, asociación o vínculo con otro(s) indicador(es) disponible(s) (ej. "¿La migración de retorno tiene relación con la natalidad o con las mujeres en educación superior?"), usa tipo_intencion = "consulta_estadistica", subtipo_consulta = "relacion_bivariada", conjunto_datos = "indicadores_departamentales", coloca exactamente los 2 o 3 indicadores numéricos pedidos en columnas_metricas (ej. ["tasa_retorno_migratorio_por_10k", "tasa_natalidad_por_1000", "pct_mujeres_superior"]) y visualizacion_sugerida = "dispersion_bivariada".
   - C) RESPUESTA PARCIAL INTELIGENTE (subtipo_consulta = "respuesta_parcial"):
     Cuando el usuario menciona dos temas y AL MENOS UNO SÍ existe en el portal pero otro NO existe (ej. "¿El desempleo tiene que ver con la migración?" o "¿Cuál tiene más migración y cuál más pobreza?"), NO rechaces toda la consulta: usa tipo_intencion = "consulta_estadistica", subtipo_consulta = "respuesta_parcial", escribe el tema faltante en indicador_no_disponible (ej. "desempleo" o "pobreza monetaria"), asigna conjunto_datos = "indicadores_departamentales" y pon en columnas_metricas los indicadores reales que SÍ existen (ej. ["tasa_retorno_migratorio_por_10k", "retornados_total"]; si pregunta por pobreza, puedes incluir adicionalmente "indice_vulnerabilidad_ivst" y "nivel_vulnerabilidad"). Solo usa tipo_intencion = "fuera_de_dominio" cuando NINGÚN tema de la pregunta exista en el portal.
   - D) TODOS LOS INDICADORES DE UN TERRITORIO:
     Cuando pidan 2 o más indicadores de un departamento (ej. "¿Cuánta población y qué nivel de vulnerabilidad tiene Huehuetenango?"), incluye TODOS esos indicadores en columnas_metricas (ej. ["poblacion_total", "nivel_vulnerabilidad", "indice_vulnerabilidad_ivst"]) y el código en codigos_departamento.
   - E) DEMOGRÁFICAS Y POSICIÓN EN RANKING:
     Para mujeres vs hombres usa conjunto_datos = "indicadores_departamentales", columnas_metricas = ["mujeres", "hombres", "poblacion_total", "indice_masculinidad"] y limite = 22. Para niños (<15 años) o adultos mayores (65+) usa columnas_metricas = ["pob_menor_15", "pct_poblacion_menor_15"] (o "pob_65_mas"), direccion_orden = "asc" para "menor" y "desc" para "mayor". Para puesto/número de ranking de un departamento, pon su código en codigos_departamento y el indicador en ordenar_por.

5. CONJUNTOS DINÁMICOS DEL CATÁLOGO LOCAL (conjunto_dinamico_slug):
   - Cuando la pregunta corresponda a uno de los conjuntos listados en "CONJUNTOS ADICIONALES PROCESADOS EN CATÁLOGO LOCAL" (por ejemplo graduados de educación superior 2025 o educación formal 2025), clasifica tipo_intencion = "consulta_estadistica", deja conjunto_datos = null, asigna conjunto_dinamico_slug y conjunto_dinamico_archivo exactos de esa lista, y elige agrupar_por_dinamico con una columna categórica apropiada de esa lista (por ejemplo Depto, Facultad, Carrera, Nivel_Edu, Sector o Sexo).

6. REGLAS PARA mensaje_contextual:
   - Redacta una sola oración breve y cortés en español para el ciudadano.
   - NUNCA menciones nombres de archivos, extensiones .parquet, nombres técnicos de columnas ni librerías internas.
"""


class ExternalAIServiceError(RuntimeError):
    """Excepcion controlada ante fallos de comunicacion o configuracion del proveedor LLM."""


class RoutingLLMClientProtocol(Protocol):
    """Contrato abstracto del cliente de enrutamiento para facilitar inyeccion y mocks."""

    def build_routing_plan(self, sanitized_query: str, dynamic_context: str = "") -> AISearchRoutingPlan: ...


class GeminiRoutingClient:
    """Cliente desacoplado para traduccion Text-to-JSON mediante Google GenAI."""

    def __init__(self, settings: AISearchSettings, sdk_client: Optional[object] = None) -> None:
        self._settings = settings
        self._sdk_client = sdk_client

    def _get_or_create_sdk_client(self) -> object:
        if self._sdk_client is not None:
            return self._sdk_client

        if self._settings.gemini_api_key is None:
            logger.error("Variable GEMINI_API_KEY ausente al intentar consultar el motor de IA.")
            raise ExternalAIServiceError("Credencial del servicio de IA no configurada.")

        try:
            from google import genai

            api_key_value = self._settings.gemini_api_key.get_secret_value()
            self._sdk_client = genai.Client(
                api_key=api_key_value,
                http_options={"timeout": self._settings.gemini_timeout_ms},
            )
            return self._sdk_client
        except Exception as exc:
            logger.error("No fue posible inicializar el cliente GenAI (%s).", type(exc).__name__)
            raise ExternalAIServiceError("Error al inicializar el cliente de IA.") from exc

    def _candidate_models(self) -> list[str]:
        ordered = [self._settings.gemini_model]
        for fallback in self._settings.gemini_fallback_models:
            if fallback and fallback not in ordered:
                ordered.append(fallback)
        return ordered

    def build_routing_plan(self, sanitized_query: str, dynamic_context: str = "") -> AISearchRoutingPlan:
        client = self._get_or_create_sdk_client()
        try:
            from google.genai import errors as genai_errors
            from google.genai import types

            sys_instruction = SYSTEM_PROMPT_TEXT_TO_JSON
            if dynamic_context.strip():
                sys_instruction = f"{SYSTEM_PROMPT_TEXT_TO_JSON}\n{dynamic_context.strip()}\n"

            config = types.GenerateContentConfig(
                system_instruction=sys_instruction,
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=AISearchRoutingPlan,
            )

            last_exc: Optional[Exception] = None
            models_to_try = self._candidate_models()
            for idx, model_name in enumerate(models_to_try):
                try:
                    response = client.models.generate_content(  # type: ignore[attr-defined]
                        model=model_name,
                        contents=sanitized_query,
                        config=config,
                    )
                    parsed = getattr(response, "parsed", None)
                    if isinstance(parsed, AISearchRoutingPlan):
                        return parsed
                    if isinstance(parsed, dict):
                        return AISearchRoutingPlan.model_validate(parsed)

                    raw_text = getattr(response, "text", None)
                    if isinstance(raw_text, str) and raw_text.strip():
                        return AISearchRoutingPlan.model_validate_json(raw_text)

                    logger.error("Respuesta vacia o sin estructura valida desde el proveedor de IA.")
                    raise ExternalAIServiceError("Respuesta invalida del proveedor de IA.")
                except genai_errors.ServerError as srv_exc:
                    last_exc = srv_exc
                    if idx + 1 < len(models_to_try):
                        logger.warning(
                            "Modelo %s temporalmente saturado (%s); reintentando con modelo de respaldo.",
                            model_name,
                            type(srv_exc).__name__,
                        )
                        continue
                    raise

            if last_exc is not None:
                raise last_exc
            raise ExternalAIServiceError("No fue posible completar el enrutamiento con IA.")
        except ExternalAIServiceError:
            raise
        except Exception as exc:
            logger.error("Fallo durante generacion estructurada con Gemini (%s).", type(exc).__name__)
            raise ExternalAIServiceError("Fallo de comunicacion con el proveedor de IA.") from exc
