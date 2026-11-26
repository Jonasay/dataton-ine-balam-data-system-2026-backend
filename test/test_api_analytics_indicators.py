from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_departmental_indicators_endpoints():
    """Verificar consulta, filtros, validaciones y detalle enriquecido departamental."""
    resp = client.get("/api/v1/indicadores/departamentales?limit=22")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_departamentos"] == 22
    assert len(payload["datos"]) == 22

    # filtro por region metropolitana
    resp_reg = client.get("/api/v1/indicadores/departamentales?region_id=1")
    assert resp_reg.status_code == 200
    assert resp_reg.json()["total_departamentos"] == 1
    assert resp_reg.json()["datos"][0]["depto_nombre"] == "Guatemala"

    # validacion de columna inexistente
    resp_bad = client.get("/api/v1/indicadores/departamentales?sort_by=columna_inexistente")
    assert resp_bad.status_code == 400

    # detalle por nombre y enriquecimiento pca/cluster
    resp_detail = client.get("/api/v1/indicadores/departamentales/Petén")
    assert resp_detail.status_code == 200
    detail = resp_detail.json()
    assert detail["depto_codigo"] == 17
    assert "cluster_nombre" in detail
    assert "pca_1" in detail

    resp_404 = client.get("/api/v1/indicadores/departamentales/DepartamentoInvalido")
    assert resp_404.status_code == 404


def test_municipal_and_methodology_endpoints():
    """Verificar endpoints municipales (340 municipios) y catalogo de 18 fichas."""
    resp = client.get("/api/v1/indicadores/municipales?depto_codigo=1&sort_by=poblacion_total&order=desc&limit=5")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_municipios"] == 17
    assert payload["datos"][0]["mupio_codigo_str"] == "0101"

    resp_single = client.get("/api/v1/indicadores/municipales/0101")
    assert resp_single.status_code == 200
    assert resp_single.json()["depto_nombre"] == "Guatemala"

    resp_bad = client.get("/api/v1/indicadores/municipales?sort_by=invalida")
    assert resp_bad.status_code == 400

    resp_cards = client.get("/api/v1/indicadores/fichas-metodologicas")
    assert resp_cards.status_code == 200
    assert resp_cards.json()["total_fichas"] == 18

    # filtro parcial para seguridad y movilidad
    resp_sec = client.get("/api/v1/indicadores/fichas-metodologicas?dominio=Seguridad")
    assert resp_sec.status_code == 200
    assert resp_sec.json()["total_fichas"] >= 1

    resp_mov = client.get("/api/v1/indicadores/fichas-metodologicas?dominio=Movilidad")
    assert resp_mov.status_code == 200
    assert resp_mov.json()["total_fichas"] >= 2


def test_analytics_endpoints_suite():
    """Verificar todos los endpoints de ciencia de datos, correlaciones, pca, clusters y proyecciones."""
    resp_desc = client.get("/api/v1/analisis/descriptivo")
    assert resp_desc.status_code == 200
    assert resp_desc.json()["total_variables"] >= 30

    resp_out = client.get("/api/v1/analisis/outliers")
    assert resp_out.status_code == 200
    assert resp_out.json()["total_outliers"] >= 10

    resp_corr = client.get("/api/v1/analisis/correlaciones?only_significant=true&min_abs_r=0.5&sort_by=pearson")
    assert resp_corr.status_code == 200
    pairs = resp_corr.json()["pares"]
    assert len(pairs) >= 1
    assert all(abs(p["pearson_r"]) >= 0.5 for p in pairs)
    abs_r = [abs(p["pearson_r"]) for p in pairs]
    assert abs_r == sorted(abs_r, reverse=True)

    resp_pca = client.get("/api/v1/analisis/pca")
    assert resp_pca.status_code == 200
    assert resp_pca.json()["varianza_acumulada_3_componentes"] >= 0.75

    resp_clust = client.get("/api/v1/analisis/clusters")
    assert resp_clust.status_code == 200
    assert resp_clust.json()["total_clusters"] == 4

    resp_cba = client.get("/api/v1/analisis/proyecciones/costo-vida")
    assert resp_cba.status_code == 200
    assert len(resp_cba.json()) == 2

    resp_demo = client.get("/api/v1/analisis/proyecciones/demograficas")
    assert resp_demo.status_code == 200
    assert len(resp_demo.json()) == 22

    resp_vuln = client.get("/api/v1/analisis/vulnerabilidad")
    assert resp_vuln.status_code == 200
    vuln = resp_vuln.json()
    assert vuln["total_departamentos"] == 22
    assert vuln["indicadores"][0]["ranking"] == 1


@patch("src.api.v1.endpoints.process_router.build_guatemala_relief_scene")
@patch("src.api.v1.endpoints.process_router.merge_geo_with_parquet")
@patch("src.api.v1.endpoints.process_router.load_geodata")
def test_api_3d_model_stl_and_obj_downloads(mock_load, mock_merge, mock_scene, tmp_path, monkeypatch):
    """Verificar descarga de modelos 3d en formatos stl y obj para mapas."""
    monkeypatch.setattr("src.api.v1.endpoints.process_router.PROCESSED_DATA_DIR", tmp_path)
    mock_scene_obj = MagicMock()
    mock_geom = MagicMock()
    mock_scene_obj.geometry = {"depto_01": mock_geom}
    mock_scene_obj.export.return_value = "v 0 0 0\nf 1 1 1\n"
    mock_scene.return_value = mock_scene_obj

    resp_obj = client.get("/api/v1/proceso/modelo-3d-impresion?ruta_geo=geo.shp&ruta_parquet=t.parquet&formato=obj")
    assert resp_obj.status_code == 200
    assert "v 0 0 0" in resp_obj.text
    assert ".obj" in resp_obj.headers.get("content-disposition", "")

    with patch("trimesh.util.concatenate") as mock_concat:
        def write_stl(path):
            Path(path).write_bytes(b"solid test\nendsolid test\n")

        mock_solid = MagicMock()
        mock_solid.export.side_effect = write_stl
        mock_concat.return_value = mock_solid

        resp_stl = client.get("/api/v1/proceso/modelo-3d-impresion?ruta_geo=geo.shp&ruta_parquet=t.parquet&formato=stl")
        assert resp_stl.status_code == 200
        assert b"solid test" in resp_stl.content
        assert ".stl" in resp_stl.headers.get("content-disposition", "")
