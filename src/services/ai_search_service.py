from __future__ import annotations

import logging
import re
from typing import Optional

from src.repositories.statistics_repository import DatasetUnavailableError, StatisticsRepository
from src.schemas.ai_search import AISearchResponse, AISearchRoutingPlan
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

# Patrones deterministas de defensa en profundidad contra consultas de datos personales (PII)
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

# Palabras tecnicas prohibidas en mensajes hacia el usuario final
_FORBIDDEN_LEAK_TERMS_RE = re.compile(
    r"(\.parquet|polars|duckdb|dataframe|scan_parquet|traceback|sql|data/processed|data/raw)",
    re.IGNORECASE,
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
    if _FORBIDDEN_LEAK_TERMS_RE.search(cleaned) or len(cleaned) > 280:
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

        # 2. Consulta en cache TTL normalizada
        cached_response = self._cache.get(sanitized_query)
        if cached_response is not None:
            return cached_response

        # 3. Traduccion estructurada Text-to-JSON mediante Gemini
        plan: AISearchRoutingPlan = self._llm_client.build_routing_plan(sanitized_query)

        # 4. Evaluacion de intenciones bloqueadas o fuera de alcance institucional
        if plan.tipo_intencion == "bloqueo_privacidad":
            response = AISearchResponse(
                mensaje=PRIVACY_BLOCK_MESSAGE,
                datos=[],
                visualizacion_url=None,
            )
            self._cache.set(sanitized_query, response)
            return response

        if plan.tipo_intencion == "fuera_de_dominio" or plan.conjunto_datos is None:
            response = AISearchResponse(
                mensaje=OUT_OF_DOMAIN_MESSAGE,
                datos=[],
                visualizacion_url=None,
            )
            self._cache.set(sanitized_query, response)
            return response

        # 5. Ejecucion en modo solo lectura sobre tablas estadisticas agregadas
        try:
            rows, vis_url = self._repository.execute_plan(plan)
        except DatasetUnavailableError as exc:
            logger.error("Fuente de datos estadisticos no disponible durante consulta (%s).", type(exc).__name__)
            raise ExternalAIServiceError("Datos estadisticos temporalmente no disponibles.") from exc

        if not rows:
            response = AISearchResponse(
                mensaje=EMPTY_RESULTS_MESSAGE,
                datos=[],
                visualizacion_url=None,
            )
            self._cache.set(sanitized_query, response)
            return response

        response = AISearchResponse(
            mensaje=sanitize_public_message(plan.mensaje_contextual),
            datos=rows,
            visualizacion_url=vis_url,
        )
        self._cache.set(sanitized_query, response)
        return response
