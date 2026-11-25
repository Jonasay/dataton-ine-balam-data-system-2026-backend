from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from main import app
from src.api.v1.endpoints.ai_search_router import (
    PUBLIC_503_MESSAGE,
    get_ai_search_service,
    limiter,
)
from src.core.ai_config import AISearchSettings
from src.core.config import PROCESSED_DATA_DIR
from src.repositories.statistics_repository import StatisticsRepository
from src.schemas.ai_search import AISearchRoutingPlan
from src.services.ai_search_service import (
    DEFAULT_SUCCESS_MESSAGE,
    EMPTY_RESULTS_MESSAGE,
    OUT_OF_DOMAIN_MESSAGE,
    PRIVACY_BLOCK_MESSAGE,
    AISearchService,
)
from src.services.gemini_client import ExternalAIServiceError, GeminiRoutingClient
from src.services.query_cache import AIQueryCache


@pytest.fixture()
def isolated_env():
    """Crear cliente de pruebas con dependencias aisladas y rate limiter reiniciado."""
    limiter.reset()
    mock_llm = MagicMock()
    repo = StatisticsRepository(base_dir=PROCESSED_DATA_DIR, max_rows=25)
    cache = AIQueryCache(maxsize=64, ttl_seconds=120)
    service = AISearchService(llm_client=mock_llm, repository=repo, cache=cache)

    app.dependency_overrides[get_ai_search_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client, mock_llm, cache
    app.dependency_overrides.clear()
    limiter.reset()


def test_valid_statistical_query_with_real_parquet_data(isolated_env):
    """Verificar consulta estadistica valida leyendo datos reales de data/processed/ y sin fugas internas."""
    client, mock_llm, _ = isolated_env
    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="consulta_estadistica",
        conjunto_datos="vulnerabilidad_departamental",
        columnas_metricas=["indice_vulnerabilidad_ivst", "tasa_retorno_migratorio_por_10k", "nivel_vulnerabilidad"],
        codigos_departamento=[13],
        ordenar_por="indice_vulnerabilidad_ivst",
        direccion_orden="desc",
        limite=5,
        visualizacion_sugerida="mapa_3d_relieve",
        mensaje_contextual="Se muestran los indicadores de vulnerabilidad y retorno migratorio de Huehuetenango.",
    )

    resp = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "¿Cuál es la vulnerabilidad y tasa de retorno migratorio en Huehuetenango?"},
    )
    assert resp.status_code == 200
    payload = resp.json()

    assert set(payload.keys()) == {"mensaje", "datos", "visualizacion_url"}
    assert len(payload["datos"]) == 1
    row = payload["datos"][0]
    assert row["departamento"] == "Huehuetenango"
    assert row["nivel_vulnerabilidad"] == "Crítica"
    assert row["indice_vulnerabilidad_territorial"] > 80.0
    assert payload["visualizacion_url"] == "/api/v1/visualizaciones/mapa/3d-relieve?indicador=indice_vulnerabilidad_ivst"

    # Principio de minima exposicion: cero nombres tecnicos internos o rutas .parquet
    serialized = resp.text.lower()
    assert ".parquet" not in serialized
    assert "polars" not in serialized
    assert "duckdb" not in serialized
    assert "indice_vulnerabilidad_ivst" not in row


def test_valid_query_returning_zero_rows_message(isolated_env):
    """Verificar mensaje institucional exacto cuando un filtro valido devuelve cero registros."""
    client, mock_llm, _ = isolated_env
    # El departamento de Guatemala (codigo 1) tiene vulnerabilidad Baja, por lo que filtrar Crítica da 0 filas
    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="consulta_estadistica",
        conjunto_datos="vulnerabilidad_departamental",
        columnas_metricas=["indice_vulnerabilidad_ivst"],
        codigos_departamento=[1],
        nivel_vulnerabilidad="Crítica",
        limite=5,
        visualizacion_sugerida="ranking_departamental",
    )

    resp = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "¿Tiene el departamento de Guatemala nivel de vulnerabilidad crítica?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mensaje"] == EMPTY_RESULTS_MESSAGE
    assert body["datos"] == []
    assert body["visualizacion_url"] is None


def test_out_of_domain_query_returns_neutral_message_and_empty_data(isolated_env):
    """Verificar guardrail institucional ante preguntas fuera de dominio (ej. deportes)."""
    client, mock_llm, _ = isolated_env
    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="fuera_de_dominio",
        conjunto_datos=None,
    )

    resp = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "¿Quién ganó el partido de fútbol de la liga nacional ayer?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mensaje"] == OUT_OF_DOMAIN_MESSAGE
    assert body["datos"] == []
    assert body["visualizacion_url"] is None


def test_personal_data_queries_are_blocked_by_privacy_guardrails(isolated_env):
    """Verificar bloqueo de privacidad tanto determinista (DPI/honorificos) como por clasificacion IA."""
    client, mock_llm, _ = isolated_env

    # Caso A: Bloqueo determinista previo al LLM (DPI / domicilio individual)
    resp_dpi = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "Necesito la dirección y datos de la persona con DPI 2456 78901 0101"},
    )
    assert resp_dpi.status_code == 200
    body_dpi = resp_dpi.json()
    assert body_dpi["mensaje"] == PRIVACY_BLOCK_MESSAGE
    assert body_dpi["datos"] == []
    assert body_dpi["visualizacion_url"] is None
    mock_llm.build_routing_plan.assert_not_called()

    # Caso B: Consulta sutil sobre individuo bloqueada por clasificacion estructurada del LLM
    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="bloqueo_privacidad",
        conjunto_datos=None,
    )
    resp_name = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "¿Aparece registrado Juan Carlos Morales en los retornados de 2024?"},
    )
    assert resp_name.status_code == 200
    body_name = resp_name.json()
    assert body_name["mensaje"] == PRIVACY_BLOCK_MESSAGE
    assert body_name["datos"] == []
    assert body_name["visualizacion_url"] is None
    mock_llm.build_routing_plan.assert_called_once()


def test_malicious_and_invalid_length_inputs_validation(isolated_env):
    """Verificar validacion estricta de longitud (3..300), caracteres de control, campos extra y sanitizacion."""
    client, mock_llm, _ = isolated_env

    # 1. Exceso de longitud (> 300 caracteres)
    resp_long = client.post("/api/v1/busqueda-ia", json={"consulta": "x" * 301})
    assert resp_long.status_code == 422

    # 2. Caracteres de control que al limpiarse dejan menos de 3 caracteres validos
    resp_ctrl = client.post("/api/v1/busqueda-ia", json={"consulta": "\x00\x01\x07 a \x1f"})
    assert resp_ctrl.status_code == 422

    # 3. Inyeccion de campos arbitrarios no permitidos en el JSON
    resp_extra = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "Población total por departamento", "sql": "SELECT * FROM users"},
    )
    assert resp_extra.status_code == 422
    mock_llm.build_routing_plan.assert_not_called()

    # 4. Sanitizacion de mensaje_contextual si el LLM intentara mencionar detalles internos
    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="consulta_estadistica",
        conjunto_datos="proyecciones_costo_vida",
        columnas_metricas=["costo_actual_percapita", "proyeccion_12_meses_gtq"],
        limite=2,
        visualizacion_sugerida="tendencia_costo_vida",
        mensaje_contextual="Leído desde data/processed/analisis/proyecciones_costo_vida.parquet usando Polars.",
    )
    resp_leak_guard = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "Proyección del costo de la canasta básica a 12 meses"},
    )
    assert resp_leak_guard.status_code == 200
    assert resp_leak_guard.json()["mensaje"] == DEFAULT_SUCCESS_MESSAGE
    assert ".parquet" not in resp_leak_guard.text.lower()


def test_ttl_cache_prevents_duplicate_llm_calls_on_normalized_queries(isolated_env):
    """Verificar que consultas repetidas con distintas mayusculas o espacios usen el cache en memoria."""
    client, mock_llm, _ = isolated_env
    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="consulta_estadistica",
        conjunto_datos="proyecciones_demograficas",
        columnas_metricas=["poblacion_2024", "poblacion_2030", "crecimiento_porcentual_total"],
        ordenar_por="crecimiento_porcentual_total",
        direccion_orden="desc",
        limite=3,
        visualizacion_sugerida="crecimiento_demografico",
        mensaje_contextual="Top 3 departamentos con mayor crecimiento demográfico proyectado a 2030.",
    )

    r1 = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "   ¿Cuáles departamentos crecerán más en población hacia 2030?  "},
    )
    r2 = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "¿cuáles   departamentos crecerán más en POBLACIÓN hacia 2030?"},
    )

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()
    assert len(r1.json()["datos"]) == 3
    assert mock_llm.build_routing_plan.call_count == 1


def test_external_ai_failure_returns_safe_503_without_internal_leaks(isolated_env):
    """Verificar codigo HTTP 503 amable cuando el proveedor de IA falla o no hay API key."""
    client, mock_llm, _ = isolated_env
    mock_llm.build_routing_plan.side_effect = ExternalAIServiceError("secret internal failure")

    resp = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "Tasa de natalidad por departamento en Guatemala"},
    )
    assert resp.status_code == 503
    assert resp.json() == {"detail": PUBLIC_503_MESSAGE}
    assert "secret" not in resp.text.lower()


def test_gemini_routing_client_uses_temperature_zero_and_structured_schema():
    """Verificar configuracion estricta de GeminiRoutingClient (gemini-2.5-flash, temperature=0.0, response_schema)."""
    fake_sdk = MagicMock()
    expected_plan = AISearchRoutingPlan(
        tipo_intencion="consulta_estadistica",
        conjunto_datos="indicadores_departamentales",
        columnas_metricas=["poblacion_total"],
        limite=5,
    )
    fake_response = MagicMock()
    fake_response.parsed = expected_plan
    fake_sdk.models.generate_content.return_value = fake_response

    settings = AISearchSettings(
        gemini_api_key=SecretStr("test-dummy-key-not-real"),
        gemini_model="gemini-2.5-flash",
    )
    routing_client = GeminiRoutingClient(settings=settings, sdk_client=fake_sdk)
    result = routing_client.build_routing_plan("Población por departamento")

    assert result == expected_plan
    call_kwargs = fake_sdk.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-flash"
    assert call_kwargs["config"].temperature == 0.0
    assert call_kwargs["config"].response_mime_type == "application/json"
    assert call_kwargs["config"].response_schema is AISearchRoutingPlan


def test_rate_limiting_returns_429_when_limit_exceeded(isolated_env):
    """Verificar que al exceder el limite por IP se responda HTTP 429 con mensaje limpio en espanol."""
    client, mock_llm, _ = isolated_env
    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="fuera_de_dominio",
    )

    limited_settings = AISearchSettings(rate_limit="2/minute")
    with patch("src.api.v1.endpoints.ai_search_router.get_ai_search_settings", return_value=limited_settings):
        assert client.post("/api/v1/busqueda-ia", json={"consulta": "Consulta de prueba uno"}).status_code == 200
        assert client.post("/api/v1/busqueda-ia", json={"consulta": "Consulta de prueba dos"}).status_code == 200
        resp_limited = client.post("/api/v1/busqueda-ia", json={"consulta": "Consulta de prueba tres"})

    assert resp_limited.status_code == 429
    assert "límite máximo de consultas" in resp_limited.json()["detail"]
