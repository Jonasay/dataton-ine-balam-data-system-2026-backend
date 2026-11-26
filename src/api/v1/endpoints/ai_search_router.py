import logging
from functools import lru_cache

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.core.ai_config import get_ai_search_settings
from src.core.config import PROCESSED_DATA_DIR
from src.repositories.statistics_repository import DatasetUnavailableError, StatisticsRepository
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


@router.get(
    "/busqueda-ia/visualizacion-dinamica",
    response_class=HTMLResponse,
    summary="Visualización interactiva local de conjuntos procesados",
)
def get_dynamic_ai_visualization(
    slug: str = Query(..., min_length=2, max_length=120),
    archivo: str = Query(..., min_length=1, max_length=160),
    agrupar_por: Optional[str] = Query(default=None, max_length=80),
    repository: StatisticsRepository = Depends(get_statistics_repository),
) -> HTMLResponse:
    """Renderizar grafica interactiva agregada directamente desde el conjunto local procesado."""
    try:
        html = repository.build_dynamic_chart_html(slug=slug, archivo=archivo, agrupar_por=agrupar_por)
        return HTMLResponse(content=html)
    except DatasetUnavailableError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visualización no disponible.")
    except Exception as exc:
        logger.error("Error generando visualizacion dinamica (%s).", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=PUBLIC_503_MESSAGE)


@router.get(
    "/busqueda-ia/visualizacion-demografica",
    response_class=HTMLResponse,
    summary="Visualización interactiva demográfica por sexo o grupo etario",
)
def get_demographic_ai_visualization(
    modo: str = Query(default="sexo", pattern="^(sexo|ranking)$"),
    columna: str = Query(default="pob_menor_15", max_length=40),
    orden: str = Query(default="asc", pattern="^(asc|desc)$"),
    top_n: int = Query(default=10, ge=3, le=22),
    repository: StatisticsRepository = Depends(get_statistics_repository),
) -> HTMLResponse:
    """Renderizar grafica comparativa demografica por sexo o edades directamente desde series agregadas."""
    try:
        html = repository.build_demographic_chart_html(modo=modo, columna=columna, orden=orden, top_n=top_n)
        return HTMLResponse(content=html)
    except DatasetUnavailableError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visualización no disponible.")
    except Exception as exc:
        logger.error("Error generando visualizacion demografica (%s).", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=PUBLIC_503_MESSAGE)


@router.get(
    "/busqueda-ia/visualizacion-dispersion",
    response_class=HTMLResponse,
    summary="Visualización de dispersión bivariada entre dos indicadores departamentales",
)
def get_bivariate_scatter_ai_visualization(
    x: str = Query(..., min_length=2, max_length=60),
    y: str = Query(..., min_length=2, max_length=60),
    repository: StatisticsRepository = Depends(get_statistics_repository),
) -> HTMLResponse:
    """Renderizar grafica de dispersion (scatter plot) etiquetada para los 22 departamentos."""
    try:
        html = repository.build_bivariate_scatter_html(x_col=x, y_col=y)
        return HTMLResponse(content=html)
    except DatasetUnavailableError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visualización no disponible.")
    except Exception as exc:
        logger.error("Error generando visualizacion de dispersion (%s).", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=PUBLIC_503_MESSAGE)
