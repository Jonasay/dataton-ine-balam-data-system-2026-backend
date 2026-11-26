import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from main import app
from src.process.process import (
    aggregate_parquet,
    create_plotly_choropleth,
    excel_to_parquet,
    export_folium_map,
    load_geodata,
    merge_geo_with_parquet,
    read_excel_sheets
)

client = TestClient(app)


def test_require_polars_error():
    """Verificar excepcion informativa cuando polars no esta instalado."""
    with patch.dict(sys.modules, {"polars": None}):
        with pytest.raises(ImportError) as exc_info:
            read_excel_sheets("archivo.xlsx")
        assert "se requiere la libreria polars" in str(exc_info.value)


@patch("src.process.process._require_polars")
def test_read_excel_sheets(mock_pl):
    """Verificar llamada de lectura a hojas de excel con polars."""
    mock_polars = MagicMock()
    mock_polars.read_excel.return_value = {"hoja1": MagicMock()}
    mock_pl.return_value = mock_polars

    result = read_excel_sheets("data/raw/prueba.xlsx", sheet_id=0)
    assert "hoja1" in result
    mock_polars.read_excel.assert_called_once()


@patch("src.process.process._require_polars")
def test_excel_to_parquet(mock_pl, tmp_path):
    """Verificar conversion de excel a parquet con compresion zstd."""
    mock_polars = MagicMock()
    mock_df = MagicMock()
    mock_polars.read_excel.return_value = mock_df
    mock_pl.return_value = mock_polars

    out_file = tmp_path / "tabla.parquet"
    created = excel_to_parquet("archivo.xlsx", out_file, sheet_id=1, compression="zstd")
    assert created == out_file
    mock_df.write_parquet.assert_called_once_with(str(out_file), compression="zstd")


@patch("src.process.process._require_polars")
def test_aggregate_parquet(mock_pl):
    """Verificar agregacion y resumen de datos de parquet sin sentencias sql."""
    mock_polars = MagicMock()
    mock_lazy = MagicMock()
    mock_result_df = MagicMock()
    mock_result_df.columns = ["depto_ocu", "conteo"]
    mock_result_df.__len__.return_value = 2
    mock_result_df.to_dicts.return_value = [
        {"depto_ocu": 1, "conteo": 500},
        {"depto_ocu": 5, "conteo": 200}
    ]

    mock_lazy.group_by.return_value = mock_lazy
    mock_lazy.len.return_value = mock_lazy
    mock_lazy.sort.return_value = mock_lazy
    mock_lazy.limit.return_value = mock_lazy
    mock_lazy.collect.return_value = mock_result_df
    mock_polars.scan_parquet.return_value = mock_lazy
    mock_pl.return_value = mock_polars

    summary = aggregate_parquet("tabla.parquet", group_by="depto_ocu", limit=10)
    assert summary["agrupado_por"] == "depto_ocu"
    assert summary["total_registros_retornados"] == 2
    assert summary["filas"][0]["conteo"] == 500


@patch("src.process.process._require_geopandas")
def test_load_geodata(mock_gpd):
    """Verificar lectura de shapefile y formateo de codigo espacial."""
    import pandas as pd
    mock_geopandas = MagicMock()
    fake_gdf = pd.DataFrame({"COD_COLUMNA": [1, 25], "nombre": ["guatemala", "peten"]})
    fake_gdf.columns = ["COD_COLUMNA", "nombre"]

    # simular to_crs devolviendo el mismo dataframe con metodo to_crs
    mock_res = MagicMock()
    mock_res.columns = ["COD_COLUMNA", "nombre"]
    mock_res.__getitem__.side_effect = fake_gdf.__getitem__
    mock_res.__setitem__.side_effect = fake_gdf.__setitem__
    mock_geopandas.read_file.return_value.to_crs.return_value = fake_gdf
    mock_gpd.return_value = mock_geopandas

    gdf = load_geodata("data/raw/geo/mapa.shp", target_crs=4326)
    assert "cod" in gdf.columns
    assert gdf["cod"].tolist() == ["01", "25"]


@patch("src.process.process._require_duckdb")
def test_merge_geo_with_parquet(mock_ddb):
    """Verificar fusion de geodatos con tabla extraida por duckdb."""
    import pandas as pd
    mock_duckdb = MagicMock()
    mock_ddb.return_value = mock_duckdb

    mock_table = pd.DataFrame({"cod": ["01"], "valor": [150]})
    mock_duckdb.sql.return_value.pl.return_value.to_pandas.return_value = mock_table

    geo_df = pd.DataFrame({"cod": ["01"], "nombre": ["guatemala"]})
    merged = merge_geo_with_parquet(geo_df, "tabla.parquet")
    assert "valor" in merged.columns
    assert merged["valor"].tolist() == [150]


@patch("src.process.process._require_folium")
def test_export_folium_map(mock_folium, tmp_path):
    """Verificar exportacion de mapa interactivo folium a html."""
    mock_gdf = MagicMock()
    mock_map = MagicMock()
    mock_gdf.columns = ["nombre", "valor"]
    mock_gdf.explore.return_value = mock_map

    out_html = tmp_path / "mapa.html"
    result_path = export_folium_map(mock_gdf, out_html)
    assert result_path == out_html
    mock_map.save.assert_called_once_with(str(out_html))


@patch("src.process.process._require_plotly")
def test_create_plotly_choropleth(mock_px):
    """Verificar construccion de mapa coropletico con plotly."""
    mock_plotly = MagicMock()
    mock_fig = MagicMock()
    mock_plotly.choropleth_map.return_value = mock_fig
    mock_px.return_value = mock_plotly

    mock_gdf = MagicMock()
    mock_gdf.columns = ["cod", "valor", "nombre"]
    mock_gdf.__geo_interface__ = {"type": "FeatureCollection"}

    fig = create_plotly_choropleth(mock_gdf)
    assert fig == mock_fig
    mock_plotly.choropleth_map.assert_called_once()


@patch("src.api.v1.endpoints.process_router.read_excel_sheets")
def test_api_get_excel_sheets(mock_read):
    """Verificar endpoint api para inspeccionar hojas de excel."""
    mock_df = MagicMock()
    mock_df.columns = ["col1", "col2"]
    mock_df.head.return_value.to_dicts.return_value = [{"col1": 10, "col2": 20}]

    mock_read.side_effect = [
        {"hoja1": MagicMock(), "hoja2": MagicMock()},
        mock_df
    ]

    response = client.get("/api/v1/proceso/hojas-excel?ruta_excel=test.xlsx&limite=5")
    assert response.status_code == 200
    data = response.json()
    assert data["archivo"] == "test.xlsx"
    assert data["hojas"] == ["hoja1", "hoja2"]
    assert len(data["filas_muestra"]) == 1


@patch("src.api.v1.endpoints.process_router.excel_to_parquet")
def test_api_post_excel_to_parquet(mock_conv, tmp_path):
    """Verificar endpoint api para convertir excel a parquet."""
    fake_parquet = tmp_path / "datos.parquet"
    fake_parquet.write_bytes(b"PARQUET_MOCK_BYTES")
    mock_conv.return_value = fake_parquet

    response = client.post(
        "/api/v1/proceso/convertir",
        json={"ruta_excel": "datos.xlsx", "hoja_id": 1, "compresion": "zstd"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mensaje"] == "archivo parquet generado exitosamente"
    assert data["tamano_bytes"] > 0


@patch("src.api.v1.endpoints.process_router.aggregate_parquet")
def test_api_parquet_summary(mock_agg):
    """Verificar endpoint api para resumen y agregacion sin sentencias sql."""
    mock_agg.return_value = {
        "archivo": "tabla.parquet",
        "agrupado_por": "depto_ocu",
        "filas": [{"depto_ocu": 1, "conteo": 5691}]
    }

    # prueba metodo get
    resp_get = client.get("/api/v1/proceso/resumen?ruta_parquet=tabla.parquet&agrupar_por=depto_ocu")
    assert resp_get.status_code == 200
    assert resp_get.json()["agrupado_por"] == "depto_ocu"

    # prueba metodo post
    resp_post = client.post(
        "/api/v1/proceso/resumen",
        json={"ruta_parquet": "tabla.parquet", "agrupar_por": "depto_ocu", "limite": 10}
    )
    assert resp_post.status_code == 200
    assert resp_post.json()["filas"][0]["conteo"] == 5691


@patch("src.api.v1.endpoints.process_router.export_folium_map")
@patch("src.api.v1.endpoints.process_router.merge_geo_with_parquet")
@patch("src.api.v1.endpoints.process_router.load_geodata")
def test_api_get_interactive_folium_map(mock_load, mock_merge, mock_export, tmp_path):
    """Verificar endpoint api para generar mapa interactivo en html."""
    fake_html = tmp_path / "mapa.html"
    fake_html.write_text("<html><body>mapa folium</body></html>")
    mock_export.return_value = fake_html

    response = client.get("/api/v1/proceso/mapa-html?ruta_geo=geo.shp&ruta_parquet=t.parquet")
    assert response.status_code == 200
    assert "<html><body>mapa folium</body></html>" in response.text


@patch("src.api.v1.endpoints.process_router.create_plotly_choropleth")
@patch("src.api.v1.endpoints.process_router.merge_geo_with_parquet")
@patch("src.api.v1.endpoints.process_router.load_geodata")
def test_api_get_plotly_choropleth_map(mock_load, mock_merge, mock_plotly, tmp_path, monkeypatch):
    """Verificar endpoint api para mapa coropletico plotly en formatos html y json."""
    monkeypatch.setattr("src.api.v1.endpoints.process_router.PROCESSED_DATA_DIR", tmp_path)
    mock_fig = MagicMock()
    mock_fig.to_html.return_value = "<div>mapa plotly</div>"
    mock_fig.to_dict.return_value = {"data": [], "layout": {}}
    mock_plotly.return_value = mock_fig

    # formato html predeterminado
    resp_html = client.get("/api/v1/proceso/mapa-plotly?ruta_geo=geo.shp&ruta_parquet=t.parquet&formato=html")
    assert resp_html.status_code == 200
    assert "<div>mapa plotly</div>" in resp_html.text

    # formato json
    resp_json = client.get("/api/v1/proceso/mapa-plotly?ruta_geo=geo.shp&ruta_parquet=t.parquet&formato=json")
    assert resp_json.status_code == 200
    assert "data" in resp_json.json()


def test_derive_topic_title():
    """Verificar deduccion automatica de titulos descriptivos a partir del nombre parquet."""
    from src.process.process import derive_topic_title

    assert derive_topic_title("data/processed/resumen_accidentes_2025.parquet") == "Accidentes 2025"
    assert derive_topic_title("datos_poblacion_censo.parquet") == "Poblacion Censo"
    assert derive_topic_title("mapa_vehiculos_involucrados.parquet") == "Vehiculos Involucrados"


def test_build_guatemala_sidebar_html_elements():
    """Verificar que el panel lateral contenga tema descriptivo, ine y boton de centrado."""
    import pandas as pd
    from src.process.process import build_guatemala_sidebar_html

    fake_df = pd.DataFrame({
        "cod": ["01", "02"],
        "nombre": ["Guatemala", "El Progreso"],
        "valor": [5000, 120]
    })

    html = build_guatemala_sidebar_html(fake_df, value_col="valor", name_col="nombre", topic_title="Accidentes de Transito")
    assert "Estadísticas de Guatemala" in html
    assert "Instituto Nacional de Estadística (INE)" in html
    assert "Accidentes de Transito" in html
    assert "🎯 Centrar" in html
    assert "centrarMapaGuatemala()" in html


def test_build_deckgl_3d_relief_html_elements():
    """Verificar que la vista 3D en deck.gl incluya panel lateral y boton centrar."""
    import pandas as pd
    from src.process.relief_3d import build_deckgl_3d_relief_html

    mock_gdf = MagicMock()
    mock_gdf.columns = ["cod", "nombre", "valor"]
    mock_gdf.__len__.return_value = 1
    mock_gdf.__getitem__.side_effect = lambda key: pd.Series([2500]) if key == "valor" else pd.Series(["Guatemala"])
    mock_gdf.sort_values.return_value = pd.DataFrame([{"nombre": "Guatemala", "valor": 2500}])
    mock_gdf.__geo_interface__ = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"cod": "01", "nombre": "Guatemala", "valor": 2500},
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        }]
    }

    html = build_deckgl_3d_relief_html(mock_gdf, value_col="valor", topic_title="Heridos 2025")
    assert "deck.gl" in html
    assert "Heridos 2025" in html
    assert "🎯 Centrar" in html
    assert "FlyToInterpolator" in html
    assert "Perspectivas y Controles 3D" in html
    assert "22 Colores" in html
    assert "Relieve Negro" in html
    assert "setPerspective" in html


@patch("src.api.v1.endpoints.process_router.build_deckgl_3d_relief_html")
@patch("src.api.v1.endpoints.process_router.merge_geo_with_parquet")
@patch("src.api.v1.endpoints.process_router.load_geodata")
def test_api_get_3d_relief_map(mock_load, mock_merge, mock_deck):
    """Verificar endpoint de mapa 3D interactivo."""
    mock_deck.return_value = "<html><body>mapa 3d deckgl</body></html>"
    response = client.get("/api/v1/proceso/mapa-3d-relieve?ruta_geo=geo.shp&ruta_parquet=resumen_2025.parquet&estilo_color=negro")
    assert response.status_code == 200
    assert "mapa 3d deckgl" in response.text


@patch("src.api.v1.endpoints.process_router.build_guatemala_relief_scene")
@patch("src.api.v1.endpoints.process_router.merge_geo_with_parquet")
@patch("src.api.v1.endpoints.process_router.load_geodata")
def test_api_get_printable_3d_model(mock_load, mock_merge, mock_scene, tmp_path):
    """Verificar endpoint de generacion de modelo 3D descargable para impresion."""
    mock_scene_obj = MagicMock()
    mock_geom = MagicMock()
    mock_geom.export.return_value = b"STL_BYTES"
    mock_scene_obj.geometry = {"depto_01": mock_geom}
    mock_scene.return_value = mock_scene_obj

    # parchear directorio procesado para prueba
    with patch("src.api.v1.endpoints.process_router.PROCESSED_DATA_DIR", tmp_path):
        def fake_export(path):
            Path(path).write_bytes(b"GLB_MOCK_BYTES")
        mock_scene_obj.export.side_effect = fake_export

        # probar formato glb (para blender)
        resp_glb = client.get("/api/v1/proceso/modelo-3d-impresion?ruta_geo=geo.shp&ruta_parquet=t.parquet&formato=glb")
        assert resp_glb.status_code == 200
        assert resp_glb.content == b"GLB_MOCK_BYTES"

        # probar formato zip (pack stl por depto)
        resp_zip = client.get("/api/v1/proceso/modelo-3d-impresion?ruta_geo=geo.shp&ruta_parquet=t.parquet&formato=zip")
        assert resp_zip.status_code == 200
        assert len(resp_zip.content) > 0


@patch("src.api.v1.endpoints.process_router.render_guatemala_with_blender")
@patch("src.api.v1.endpoints.process_router.build_guatemala_relief_scene")
@patch("src.api.v1.endpoints.process_router.merge_geo_with_parquet")
@patch("src.api.v1.endpoints.process_router.load_geodata")
def test_api_get_blender_3d_render(mock_load, mock_merge, mock_scene, mock_render, tmp_path):
    """Verificar endpoint de renderizado con Blender headless."""
    mock_scene_obj = MagicMock()
    mock_scene.return_value = mock_scene_obj

    with patch("src.api.v1.endpoints.process_router.PROCESSED_DATA_DIR", tmp_path):
        def fake_render(*args, **kwargs):
            out_p = kwargs.get("output_png_path") or args[1]
            Path(out_p).write_bytes(b"PNG_MOCK_RENDER")
            return Path(out_p)
        mock_render.side_effect = fake_render

        response = client.get("/api/v1/proceso/render-3d-blender?ruta_geo=geo.shp&ruta_parquet=t.parquet&estilo_color=negro")
        assert response.status_code == 200
        assert response.content == b"PNG_MOCK_RENDER"


def test_api_get_map_indicators():
    """Verificar catalogo de indicadores departamentales para mapas."""
    response = client.get("/api/v1/proceso/indicadores-mapa")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["indicadores"]) == data["total"]
    first = data["indicadores"][0]
    for field in ["id", "tema", "indicador", "periodo", "ruta_parquet", "columna_codigo_parquet", "columna_valor", "titulo_mapa"]:
        assert field in first


def test_api_plotly_map_json_serializes_ndarray(tmp_path, monkeypatch):
    """Verificar serializacion json cuando plotly figura contiene arreglos numpy."""
    import numpy as np
    monkeypatch.setattr("src.api.v1.endpoints.process_router.PROCESSED_DATA_DIR", tmp_path)
    with patch("src.api.v1.endpoints.process_router.load_geodata"), \
         patch("src.api.v1.endpoints.process_router.merge_geo_with_parquet"), \
         patch("src.api.v1.endpoints.process_router.create_plotly_choropleth") as mock_plotly:
        mock_fig = MagicMock()
        mock_fig.to_dict.return_value = {"data": [{"z": np.array([1.5, 2.5])}], "layout": {}}
        mock_plotly.return_value = mock_fig

        resp = client.get("/api/v1/proceso/mapa-plotly?ruta_geo=geo.shp&ruta_parquet=t.parquet&formato=json")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["data"][0]["z"] == [1.5, 2.5]


def test_api_analyze_dataset_verifies_cache_and_builds_charts(tmp_path, monkeypatch):
    """Verificar procesamiento de conjunto, generacion de graficas y no re-descarga."""
    raw_dir = tmp_path / "raw"
    proc_dir = tmp_path / "processed"
    monkeypatch.setattr("src.api.v1.endpoints.process_router.RAW_DATA_DIR", raw_dir)
    monkeypatch.setattr("src.api.v1.endpoints.process_router.PROCESSED_DATA_DIR", proc_dir)

    mock_resources = [
        {
            "id": "res-hidro-1",
            "nombre": "Monitoreo Agua.csv",
            "formato": "csv",
            "url": "https://datos.ine.gob.gt/files/monitoreo.csv",
            "dataset": "recursos-hidricos",
        }
    ]

    def fake_download(resource, base_dir=raw_dir):
        target = base_dir / "recursos-hidricos" / "monitoreo.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "departamento,licencia,caudal\nGuatemala,Si,120\nGuatemala,No,80\nPetén,Si,95\n",
            encoding="utf-8",
        )
        return target

    with patch("src.api.v1.endpoints.ine_router.get_cached_or_fetch_resources", return_value=mock_resources), \
         patch("src.api.v1.endpoints.process_router.download_resource_file", side_effect=fake_download) as mock_dl:
        # primera llamada: descarga una vez y procesa parquet + graficas
        r1 = client.get("/api/v1/proceso/dataset/recursos-hidricos/analizar")
        assert r1.status_code == 200
        body1 = r1.json()
        assert body1["ya_estaba_descargado"] is False
        assert body1["ya_estaba_procesado"] is False
        assert body1["total_filas"] == 3
        assert len(body1["graficas"]) >= 2
        assert mock_dl.call_count == 1

        # segunda llamada: reutiliza archivo descargado y parquet procesado sin volver a descargar
        r2 = client.get("/api/v1/proceso/dataset/recursos-hidricos/analizar")
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["ya_estaba_descargado"] is True
        assert body2["ya_estaba_procesado"] is True
        assert mock_dl.call_count == 1

        # grafica interactiva plotly html
        r_html = client.get("/api/v1/proceso/dataset/recursos-hidricos/grafica?indice_grafica=0")
        assert r_html.status_code == 200
        assert "plotly" in r_html.text.lower()

