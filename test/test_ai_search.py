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


def _assert_zero_snake_case_headers(datos: list[dict]) -> None:
    for row in datos:
        for key in row.keys():
            assert "_" not in key, f"Se encontro encabezado en snake_case: {key}"


def test_valid_statistical_query_with_real_parquet_data(isolated_env):
    """Verificar consulta estadistica valida con todas las columnas pedidas en tabla, resumen y cero snake_case."""
    client, mock_llm, _ = isolated_env
    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="consulta_estadistica",
        conjunto_datos="vulnerabilidad_departamental",
        columnas_metricas=["poblacion_total", "indice_vulnerabilidad_ivst", "nivel_vulnerabilidad"],
        codigos_departamento=[13],
        ordenar_por="indice_vulnerabilidad_ivst",
        direccion_orden="desc",
        limite=5,
        visualizacion_sugerida="mapa_3d_relieve",
        mensaje_contextual="Se muestran los indicadores oficiales de Huehuetenango.",
    )

    resp = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "¿Cuánta población y qué nivel de vulnerabilidad tiene Huehuetenango?"},
    )
    assert resp.status_code == 200
    payload = resp.json()

    assert set(payload.keys()) == {"mensaje", "datos", "visualizacion_url"}
    assert len(payload["datos"]) == 1
    _assert_zero_snake_case_headers(payload["datos"])

    row = payload["datos"][0]
    assert row["Departamento"] == "Huehuetenango"
    assert row["Nivel de vulnerabilidad"] == "Crítica"
    assert isinstance(row["Población total"], int) and row["Población total"] > 1_000_000
    assert row["Índice de vulnerabilidad (IVST)"] > 80.0

    # Todos los indicadores solicitados aparecen citados explicitamente en el resumen superior
    assert "Población total:" in payload["mensaje"]
    assert "Nivel de vulnerabilidad: Crítica" in payload["mensaje"]
    assert "Índice de vulnerabilidad (IVST):" in payload["mensaje"]
    assert payload["visualizacion_url"] == "/api/v1/visualizaciones/mapa/3d-relieve?indicador=indice_vulnerabilidad_ivst"

    serialized = resp.text.lower()
    assert ".parquet" not in serialized
    assert "polars" not in serialized
    assert "duckdb" not in serialized


def test_multi_query_independent_indicators_answers_both_without_correlation_matrix(isolated_env):
    """Verificar A) Multi-consulta independiente: responde ambos indicadores sin redirigir a matriz_correlaciones."""
    client, mock_llm, _ = isolated_env
    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="consulta_estadistica",
        subtipo_consulta="multi_consulta",
        conjunto_datos="indicadores_departamentales",
        columnas_metricas=["inflacion_regional_interanual", "mujeres_matriculadas_superior", "pct_mujeres_superior"],
        ordenar_por="mujeres_matriculadas_superior",
        direccion_orden="desc",
        limite=10,
        visualizacion_sugerida="ranking_departamental",
    )

    resp = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "¿Qué región tiene más inflación y qué departamento tiene más mujeres en la universidad?"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["datos"]) >= 10
    _assert_zero_snake_case_headers(payload["datos"])

    first_row = payload["datos"][0]
    assert "Inflación interanual (%)" in first_row
    assert "Mujeres en educación superior" in first_row
    assert "Mujeres en educación superior (%)" in first_row
    assert "correlaciones/heatmap" not in (payload["visualizacion_url"] or "")
    assert "Inflación interanual (%)" in payload["mensaje"]
    assert "región" in payload["mensaje"].lower()
    assert "Mujeres en educación superior" in payload["mensaje"]


def test_bivariate_correlation_between_available_indicators_uses_polars_and_scatter(isolated_env):
    """Verificar B) Relacion bivariada: Pearson solo del par pedido, 22 deptos reales, aviso no-causalidad y scatter."""
    client, mock_llm, _ = isolated_env
    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="consulta_estadistica",
        subtipo_consulta="relacion_bivariada",
        conjunto_datos="indicadores_departamentales",
        columnas_metricas=[
            "tasa_retorno_migratorio_por_10k",
            "tasa_natalidad_por_1000",
            "pct_mujeres_superior",
        ],
        visualizacion_sugerida="dispersion_bivariada",
    )

    resp = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "¿La migración de retorno tiene relación con la natalidad o con las mujeres en educación superior?"},
    )
    assert resp.status_code == 200
    payload = resp.json()

    # Tabla con los 22 departamentos y nombres legibles (nunca la matriz 10x10 sin filtrar)
    assert len(payload["datos"]) == 22
    _assert_zero_snake_case_headers(payload["datos"])
    sample_row = payload["datos"][0]
    assert "Departamento" in sample_row
    assert "Tasa de retorno migratorio (x10k hab.)" in sample_row
    assert "Tasa de natalidad (x1,000 hab.)" in sample_row
    assert "Mujeres en educación superior (%)" in sample_row
    assert "Indicador A" not in sample_row

    # Resumen con lideres, fuerza de asociacion real y nota rigurosa de no causalidad
    msg = payload["mensaje"]
    assert any(level in msg for level in ("nula", "débil", "moderada", "fuerte"))
    assert "r =" in msg
    assert "lidera" in msg
    assert "no implica necesariamente causalidad" in msg

    # Grafica de dispersion etiquetada con los 22 departamentos
    assert "/api/v1/busqueda-ia/visualizacion-dispersion?" in (payload["visualizacion_url"] or "")
    viz_resp = client.get(payload["visualizacion_url"])
    assert viz_resp.status_code == 200
    assert "text/html" in viz_resp.headers["content-type"]
    assert "Huehuetenango" in viz_resp.text
    assert "Guatemala" in viz_resp.text
    assert "Nivel de vulnerabilidad" in viz_resp.text


def test_partial_smart_response_delivers_available_data_and_clarifies_missing_topic(isolated_env):
    """Verificar C) Respuesta parcial inteligente cuando un tema existe (migracion) y otro no (desempleo / pobreza)."""
    client, mock_llm, _ = isolated_env

    # Caso 1: Clasificado como respuesta_parcial directamente
    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="consulta_estadistica",
        subtipo_consulta="respuesta_parcial",
        conjunto_datos="indicadores_departamentales",
        columnas_metricas=["tasa_retorno_migratorio_por_10k", "retornados_total"],
        ordenar_por="tasa_retorno_migratorio_por_10k",
        direccion_orden="desc",
        limite=5,
        indicador_no_disponible="desempleo",
    )
    r1 = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "¿El desempleo tiene que ver con la migración?"},
    )
    assert r1.status_code == 200
    b1 = r1.json()
    assert len(b1["datos"]) == 5
    _assert_zero_snake_case_headers(b1["datos"])
    assert "desempleo" in b1["mensaje"].lower()
    assert "Tasa de retorno migratorio (x10k hab.)" in b1["datos"][0]

    # Caso 2: Defensa en profundidad si el LLM devolviera fuera_de_dominio pero existe migracion + menciona pobreza
    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="fuera_de_dominio",
        conjunto_datos=None,
        indicador_no_disponible="pobreza monetaria",
    )
    r2 = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "¿Cuál departamento tiene más migración y cuál más pobreza?"},
    )
    assert r2.status_code == 200
    b2 = r2.json()
    assert len(b2["datos"]) >= 5
    _assert_zero_snake_case_headers(b2["datos"])
    assert "pobreza monetaria" in b2["mensaje"].lower()
    assert "Índice de Vulnerabilidad Socioeconómica Territorial (IVST)" in b2["mensaje"]
    assert "Índice de vulnerabilidad (IVST)" in b2["datos"][0]


def test_valid_query_returning_zero_rows_message(isolated_env):
    """Verificar mensaje institucional exacto cuando un filtro valido devuelve cero registros."""
    client, mock_llm, _ = isolated_env
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
    """Verificar guardrail institucional ante preguntas totalmente fuera de dominio (ej. deportes)."""
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

    assert client.post("/api/v1/busqueda-ia", json={"consulta": "x" * 301}).status_code == 422
    assert client.post("/api/v1/busqueda-ia", json={"consulta": "\x00\x01\x07 a \x1f"}).status_code == 422
    resp_extra = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "Población total por departamento", "sql": "SELECT * FROM users"},
    )
    assert resp_extra.status_code == 422
    mock_llm.build_routing_plan.assert_not_called()

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
    """Verificar configuracion estricta de GeminiRoutingClient (temperature=0.0, response_schema)."""
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
        gemini_model="gemini-3.1-flash-lite",
    )
    routing_client = GeminiRoutingClient(settings=settings, sdk_client=fake_sdk)
    result = routing_client.build_routing_plan("Población por departamento")

    assert result == expected_plan
    call_kwargs = fake_sdk.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-3.1-flash-lite"
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


def test_single_department_top_1_and_plotly_ranking_chart_formatting(isolated_env):
    """Verificar formato entero (:,.0f), orden estricto, margenes, altura dinamica y leyenda limpia en Plotly."""
    client, mock_llm, _ = isolated_env
    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="consulta_estadistica",
        conjunto_datos="indicadores_departamentales",
        columnas_metricas=["matriculados_superior_total"],
        ordenar_por="matriculados_superior_total",
        direccion_orden="desc",
        limite=1,
        visualizacion_sugerida="ranking_departamental",
        mensaje_contextual="Se presenta el departamento con mayor matrícula en educación superior.",
    )

    resp = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "Cual es el departamento que tiene mayor numero de personas matriculadas en la educacion superior"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["datos"]) == 1
    assert payload["datos"][0]["Departamento"] == "Guatemala"
    assert payload["datos"][0]["Matrícula en educación superior"] > 100000

    # Validar especificacion Plotly en Top 5 (conteo entero) y Top 22 (tasa con 2 decimales)
    r_top5 = client.get(f"{payload['visualizacion_url']}&formato=json")
    assert r_top5.status_code == 200
    spec5 = r_top5.json()["plotly_spec"]
    layout5 = spec5["layout"]
    assert layout5["height"] >= 420
    assert layout5["margin"]["r"] >= 110
    assert layout5["yaxis"]["categoryorder"] == "total ascending"
    assert layout5["legend"]["title"]["text"] == "Nivel de vulnerabilidad"
    assert spec5["data"][0]["texttemplate"] == "%{text:,.0f}"
    assert spec5["data"][0]["cliponaxis"] is False
    mean_annot = next(a for a in layout5["annotations"] if "Media Nacional" in a["text"])
    assert mean_annot["y"] == 1.04
    assert mean_annot["yref"] == "paper"
    assert mean_annot["yanchor"] == "bottom"
    assert ".00" not in mean_annot["text"]

    r_top22 = client.get(
        "/api/v1/visualizaciones/barras/ranking-departamental"
        "?indicador=tasa_retorno_migratorio_por_10k&top_n=22&orden=desc&formato=json"
    )
    assert r_top22.status_code == 200
    spec22 = r_top22.json()["plotly_spec"]
    assert spec22["layout"]["height"] >= 680
    assert spec22["data"][0]["texttemplate"] == "%{text:,.2f}"


def test_children_lowest_department_and_women_vs_men_queries(isolated_env):
    """Verificar consultas intactas de desglose demografico por edad (<15) y sexo (mujeres vs hombres)."""
    client, mock_llm, _ = isolated_env

    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="consulta_estadistica",
        conjunto_datos="indicadores_departamentales",
        columnas_metricas=["pob_menor_15", "pct_poblacion_menor_15"],
        ordenar_por="pob_menor_15",
        direccion_orden="asc",
        limite=1,
        visualizacion_sugerida="ranking_departamental",
        mensaje_contextual="Se muestra el departamento con menor población infantil.",
    )
    r_kids = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "¿Cuáles es el departamento con menor cantidad de niños?"},
    )
    assert r_kids.status_code == 200
    body_kids = r_kids.json()
    _assert_zero_snake_case_headers(body_kids["datos"])
    assert body_kids["datos"][0]["Departamento"] == "El Progreso"
    assert "Población menor de 15 años" in body_kids["datos"][0]
    assert client.get(body_kids["visualizacion_url"]).status_code == 200

    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="consulta_estadistica",
        conjunto_datos="indicadores_departamentales",
        columnas_metricas=["mujeres", "hombres", "poblacion_total", "indice_masculinidad"],
        ordenar_por="poblacion_total",
        direccion_orden="desc",
        limite=22,
        visualizacion_sugerida="ranking_departamental",
        mensaje_contextual="Distribución departamental de mujeres y hombres.",
    )
    r_sex = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "poblacion de mujeres vs hombres?"},
    )
    assert r_sex.status_code == 200
    body_sex = r_sex.json()
    assert len(body_sex["datos"]) == 22
    _assert_zero_snake_case_headers(body_sex["datos"])
    assert "Población de mujeres" in body_sex["datos"][0]
    assert "Población de hombres" in body_sex["datos"][0]
    assert "Total nacional proyectado:" in body_sex["mensaje"]
    assert client.get(body_sex["visualizacion_url"]).status_code == 200


def test_specific_department_rank_and_dynamic_graduation_queries(isolated_env):
    """Verificar consulta de posicion departamental y conjuntos dinamicos procesados sin snake_case."""
    client, mock_llm, _ = isolated_env

    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="consulta_estadistica",
        conjunto_datos="indicadores_departamentales",
        columnas_metricas=["tasa_retorno_migratorio_por_10k"],
        codigos_departamento=[9],
        ordenar_por="tasa_retorno_migratorio_por_10k",
        direccion_orden="desc",
        limite=1,
        visualizacion_sugerida="ranking_departamental",
        mensaje_contextual="Se presenta la tasa de retorno migratorio de Quetzaltenango.",
    )
    resp_rank = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "Quetzaltenango en que numero se encuentra del indice migratorio?"},
    )
    assert resp_rank.status_code == 200
    p_rank = resp_rank.json()
    _assert_zero_snake_case_headers(p_rank["datos"])
    row = p_rank["datos"][0]
    assert row["Departamento"] == "Quetzaltenango"
    assert f"posición #{row['Posición']} de 22 departamentos" in p_rank["mensaje"]
    assert "top_n=22" in p_rank["visualizacion_url"]

    mock_llm.build_routing_plan.return_value = AISearchRoutingPlan(
        tipo_intencion="consulta_estadistica",
        conjunto_datos=None,
        conjunto_dinamico_slug="educacion-superior-graduados",
        conjunto_dinamico_archivo="graduados_educacion_superior-2025_hoja1",
        agrupar_por_dinamico="Depto",
        limite=10,
        mensaje_contextual="Se muestra el desglose agregado de personas graduadas en educación superior en 2025.",
    )
    resp_dyn = client.post(
        "/api/v1/busqueda-ia",
        json={"consulta": "Cuantas personas se graduaron el 2025"},
    )
    assert resp_dyn.status_code == 200
    p_dyn = resp_dyn.json()
    _assert_zero_snake_case_headers(p_dyn["datos"])
    assert "26,744 registros" in p_dyn["mensaje"]
    assert "Cantidad de registros" in p_dyn["datos"][0]
