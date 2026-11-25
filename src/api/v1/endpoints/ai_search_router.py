import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.core.ai_config import get_ai_search_settings
from src.core.config import PROCESSED_DATA_DIR
from src.repositories.statistics_repository import StatisticsRepository
from src.schemas.ai_search import AISearchRequest, AISearchResponse
from src.services.ai_search_service import AISearchService
from src.services.gemini_client import ExternalAIServiceError, GeminiRoutingClient
from src.services.query_cache import AIQueryCache

logger = logging.getLogger(__name__)

PUBLIC_503_MESSAGE = (
    "El servicio de búsqueda inteligente no se encuentra disponible temporalmente. "
    "Por favor, intente nuevamente en unos momentos."
)


def _dynamic_rate_limit() -> str:
    return get_ai_search_settings().rate_limit


limiter = Limiter(key_func=get_remote_address)

router = APIRouter(
    tags=["Búsqueda Inteligente con IA"],
)


@lru_cache(maxsize=1)
def get_shared_query_cache() -> AIQueryCache:
    settings = get_ai_search_settings()
    return AIQueryCache(
        maxsize=settings.cache_maxsize,
        ttl_seconds=settings.cache_ttl_seconds,
    )


def get_statistics_repository() -> StatisticsRepository:
    settings = get_ai_search_settings()
    return StatisticsRepository(
        base_dir=PROCESSED_DATA_DIR,
        max_rows=settings.max_rows_per_query,
    )


def get_gemini_routing_client() -> GeminiRoutingClient:
    settings = get_ai_search_settings()
    return GeminiRoutingClient(settings=settings)


def get_ai_search_service(
    llm_client: GeminiRoutingClient = Depends(get_gemini_routing_client),
    repository: StatisticsRepository = Depends(get_statistics_repository),
    cache: AIQueryCache = Depends(get_shared_query_cache),
) -> AISearchService:
    return AISearchService(
        llm_client=llm_client,
        repository=repository,
        cache=cache,
    )


@router.post(
    "/busqueda-ia",
    response_model=AISearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Búsqueda inteligente de estadísticas oficiales agregadas (Text-to-JSON)",
    description=(
        "Permite consultar en lenguaje natural los indicadores socioeconómicos, demográficos, "
        "de costo de vida, educación, seguridad vial y vulnerabilidad territorial publicados en el portal. "
        "Aplica traducción estructurada Text-to-JSON en modo solo lectura, caché con TTL, "
        "protección de privacidad por diseño y límite de peticiones por dirección IP."
    ),
    responses={
        200: {"description": "Consulta procesada correctamente con datos agregados o aviso informativo."},
        422: {"description": "La consulta enviada no cumple el formato o longitud permitida (3 a 300 caracteres)."},
        429: {"description": "Se superó el límite máximo de consultas permitidas por minuto desde esta IP."},
        503: {"description": "El motor de inteligencia artificial o las fuentes agregadas no están disponibles temporalmente."},
    },
)
@limiter.limit(_dynamic_rate_limit)
def post_ai_statistical_search(
    request: Request,
    payload: AISearchRequest,
    service: AISearchService = Depends(get_ai_search_service),
) -> AISearchResponse:
    """Procesar consulta ciudadana en lenguaje natural devolviendo estadisticas agregadas seguras."""
    try:
        return service.search(payload.consulta)
    except ExternalAIServiceError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=PUBLIC_503_MESSAGE,
        )
    except Exception as exc:
        logger.error("Error inesperado en busqueda-ia (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=PUBLIC_503_MESSAGE,
        )
