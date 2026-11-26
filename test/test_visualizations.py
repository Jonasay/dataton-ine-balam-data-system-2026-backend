from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_visualizations_catalog_endpoint():
    # verificar catalogo maestro de visualizaciones e indicadores
    res = client.get("/api/v1/visualizaciones/catalogo")
    assert res.status_code == 200
    payload = res.json()
    assert payload["total_visualizaciones"] >= 15
    assert payload["total_indicadores"] >= 15
    ids = [item["id_visualizacion"] for item in payload["visualizaciones"]]
    assert "3d_trayectoria_demografica" in ids
    assert "mapa_3d_relieve" in ids
    assert "render_3d_blender" in ids


def test_3d_interactive_charts_json_and_html():
    # validar graficas 3d animadas, pca y dispersion multidimensional en html directo y json
    endpoints = [
        "/api/v1/visualizaciones/3d/trayectoria-demografica",
        "/api/v1/visualizaciones/3d/clusters-pca",
        "/api/v1/visualizaciones/3d/riesgo-multidimensional",
        "/api/v1/visualizaciones/3d/trayectoria-costo-vida",
    ]
    for ep in endpoints:
        # por defecto el get directo retorna html listo para visualizar
        r_default = client.get(ep)
        assert r_default.status_code == 200
        assert "plotly" in r_default.text.lower()

        r_json = client.get(f"{ep}?formato=json")
        assert r_json.status_code == 200
        body = r_json.json()
        assert "plotly_spec" in body
        assert len(body["plotly_spec"]["data"]) >= 1


def test_bars_pie_trends_heatmap_radar_endpoints():
    # verificar graficas de barras, pastel, sunburst, tendencias, correlaciones y radar
    endpoints = [
        "/api/v1/visualizaciones/barras/ranking-departamental?indicador=tasa_retorno_migratorio_por_10k",
        "/api/v1/visualizaciones/barras/ranking-municipal?indicador=tasa_necropsias_por_100k&top_n=10",
        "/api/v1/visualizaciones/barras/estructura-demografica",
        "/api/v1/visualizaciones/barras/composicion-retornados?top_n=8",
        "/api/v1/visualizaciones/pastel/distribucion?tipo=clusters",
        "/api/v1/visualizaciones/pastel/distribucion?tipo=retornados_edad&depto_codigo=13",
        "/api/v1/visualizaciones/pastel/distribucion?tipo=jerarquia_territorial&metrica=poblacion_total",
        "/api/v1/visualizaciones/tendencias/costo-vida",
        "/api/v1/visualizaciones/tendencias/ipc?vista=regiones",
        "/api/v1/visualizaciones/tendencias/crecimiento-demografico?top_n=5",
        "/api/v1/visualizaciones/correlaciones/heatmap?metodo=pearson",
        "/api/v1/visualizaciones/outliers/boxplot",
        "/api/v1/visualizaciones/perfil/radar?depto_codigo=13&comparar_con=1",
    ]
    for ep in endpoints:
        r_html = client.get(ep)
        assert r_html.status_code == 200, f"fallo html directo {ep}: {r_html.text}"
        assert "plotly" in r_html.text.lower()

        sep = "&" if "?" in ep else "?"
        r_json = client.get(f"{ep}{sep}formato=json")
        assert r_json.status_code == 200, f"fallo json {ep}: {r_json.text}"
        assert "plotly_spec" in r_json.json()


def test_maps_3d_relief_and_portal_endpoints():
    # validar redireccion raiz, integracion de mapas 2d, relieve 3d deck.gl y portal unificado
    r_root = client.get("/", follow_redirects=False)
    assert r_root.status_code in (302, 307)
    assert "/visualizaciones/stack-completo" in r_root.headers["location"]

    r_portal = client.get("/api/v1/visualizaciones/stack-completo")
    assert r_portal.status_code == 200
    assert "Balam Data Systems" in r_portal.text

    r_folium = client.get("/api/v1/visualizaciones/mapa/2d-folium?indicador=tasa_necropsias_por_100k")
    assert r_folium.status_code == 200
    assert "Estadísticas de Guatemala" in r_folium.text

    r_plotly_json = client.get("/api/v1/visualizaciones/mapa/2d-plotly?indicador=indice_vulnerabilidad_ivst&formato=json")
    assert r_plotly_json.status_code == 200
    assert "plotly_spec" in r_plotly_json.json()

    r_deck = client.get("/api/v1/visualizaciones/mapa/3d-relieve?indicador=tasa_retorno_migratorio_por_10k")
    assert r_deck.status_code == 200
    assert "deck.gl" in r_deck.text
    assert "62.09" in r_deck.text


def test_3d_model_export_and_blender_route(tmp_path, monkeypatch):
    # validar exportacion glb real y ruta de renderizado blender en directorio aislado
    r_glb = client.get("/api/v1/visualizaciones/mapa/modelo-3d?indicador=tasa_retorno_migratorio_por_10k&formato=glb")
    assert r_glb.status_code == 200
    assert r_glb.content.startswith(b"glTF")

    monkeypatch.setattr("src.api.v1.endpoints.visualizations_router.PROCESSED_DATA_DIR", tmp_path)
    with patch("src.api.v1.endpoints.visualizations_router.render_guatemala_with_blender") as mock_render:
        def fake_png(*args, **kwargs):
            out_p = Path(kwargs["output_png_path"])
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_bytes(b"\x89PNG\r\n\x1a\nMOCK")
            return out_p

        mock_render.side_effect = fake_png
        r_blend = client.get("/api/v1/visualizaciones/mapa/render-blender?indicador=indice_vulnerabilidad_ivst&regenerar=true")
        assert r_blend.status_code == 200
        assert r_blend.content.startswith(b"\x89PNG")
