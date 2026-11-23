from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.core.config import PROCESSED_DATA_DIR, RAW_DATA_DIR


def _require_polars() -> Any:
    """Importar polars de forma diferida con mensaje informativo."""
    try:
        import polars as pl
        return pl
    except ImportError as exc:
        raise ImportError(
            "se requiere la libreria polars y un motor de excel (ej. fastexcel o openpyxl). "
            "instale con: pip install polars fastexcel"
        ) from exc


def _require_duckdb() -> Any:
    """Importar duckdb de forma diferida con mensaje informativo."""
    try:
        import duckdb
        return duckdb
    except ImportError as exc:
        raise ImportError(
            "se requiere la libreria duckdb para consultas analiticas. "
            "instale con: pip install duckdb"
        ) from exc


def _require_geopandas() -> Any:
    """Importar geopandas de forma diferida con mensaje informativo."""
    try:
        import geopandas as gpd
        return gpd
    except ImportError as exc:
        raise ImportError(
            "se requiere geopandas para procesamiento espacial. "
            "instale con: pip install geopandas"
        ) from exc


def _require_folium() -> Any:
    """Importar folium y mapclassify de forma diferida con mensaje informativo."""
    try:
        import folium
        import mapclassify
        return folium
    except ImportError as exc:
        raise ImportError(
            "se requiere folium y mapclassify para la exportacion de mapas html. "
            "instale con: pip install folium mapclassify"
        ) from exc


def _require_plotly() -> Any:
    """Importar plotly express de forma diferida con mensaje informativo."""
    try:
        import plotly.express as px
        return px
    except ImportError as exc:
        raise ImportError(
            "se requiere plotly para visualizaciones interactivas. "
            "instale con: pip install plotly"
        ) from exc


def _resolve_raw_path(file_path: Union[str, Path]) -> Path:
    """Resolver ruta de archivo en directorio raw buscando coincidencias si es necesario."""
    path = Path(file_path)
    if path.is_absolute() and path.exists():
        return path

    direct_path = RAW_DATA_DIR / path
    if direct_path.exists():
        return direct_path

    # buscar coincidencia por nombre de archivo dentro de subcarpetas en raw
    file_name = path.name
    matches = list(RAW_DATA_DIR.rglob(file_name))
    if matches:
        return matches[0]

    return direct_path


def read_excel_sheets(
    file_path: Union[str, Path],
    sheet_id: Union[int, str] = 0
) -> Any:
    """Leer libros de excel mediante polars devolviendo hojas o dataframes individuales."""
    pl = _require_polars()
    resolved_path = _resolve_raw_path(file_path)

    # ejecutar lectura de libro o de hoja especifica con polars
    return pl.read_excel(str(resolved_path), sheet_id=sheet_id)


def excel_to_parquet(
    excel_path: Union[str, Path],
    output_parquet_path: Union[str, Path],
    sheet_id: Union[int, str] = 1,
    compression: str = "zstd"
) -> Path:
    """Convertir una hoja de archivo excel a formato parquet optimizado con compresion zstd."""
    pl = _require_polars()
    input_path = _resolve_raw_path(excel_path)

    output_path = Path(output_parquet_path)
    if not output_path.is_absolute():
        output_path = PROCESSED_DATA_DIR / output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # leer datos de la hoja seleccionada y persistir en formato parquet
    dataframe = pl.read_excel(str(input_path), sheet_id=sheet_id)
    dataframe.write_parquet(str(output_path), compression=compression)
    return output_path


def aggregate_parquet(
    parquet_path: Union[str, Path],
    group_by: str,
    filter_col: Optional[str] = None,
    filter_val: Optional[Any] = None,
    limit: int = 10
) -> Dict[str, Any]:
    """Resumir y agrupar registros de parquet de forma eficiente sin requerir sql."""
    pl = _require_polars()
    path = Path(parquet_path)
    if not path.is_absolute():
        path = PROCESSED_DATA_DIR / path

    lazy_df = pl.scan_parquet(str(path))
    if filter_col is not None and filter_val is not None:
        lazy_df = lazy_df.filter(pl.col(filter_col) == filter_val)

    # agrupar, contar y ordenar de mayor a menor cantidad
    result_df = (
        lazy_df
        .group_by(group_by)
        .len(name="conteo")
        .sort("conteo", descending=True)
        .limit(limit)
        .collect()
    )

    return {
        "archivo": path.name,
        "agrupado_por": group_by,
        "filtro_aplicado": {filter_col: filter_val} if filter_col else None,
        "total_registros_retornados": len(result_df),
        "columnas": result_df.columns,
        "filas": result_df.to_dicts()
    }


def load_geodata(
    geo_path: Union[str, Path],
    target_crs: int = 4326,
    code_col: str = "COD_COLUMNA",
    code_length: int = 2
) -> Any:
    """Cargar archivo espacial shapefile o geojson normalizando coordenadas y codigos."""
    gpd = _require_geopandas()
    path = _resolve_raw_path(geo_path)

    # leer capa geografica y reproyectar a sistema de coordenadas wgs84
    geodataframe = gpd.read_file(str(path)).to_crs(target_crs)

    # formatear codigo con relleno de ceros a la izquierda para emparejamiento
    if code_col in geodataframe.columns:
        geodataframe["cod"] = geodataframe[code_col].astype(str).str.zfill(code_length)

    return geodataframe


def merge_geo_with_parquet(
    geo_df: Any,
    parquet_path: Union[str, Path],
    code_col: str = "cod",
    value_col: str = "valor"
) -> Any:
    """Unir capa geografica con datos analiticos extraidos de parquet mediante duckdb."""
    duckdb = _require_duckdb()
    path = Path(parquet_path)
    if not path.is_absolute():
        path = PROCESSED_DATA_DIR / path

    # extraer tabla analitica con duckdb y convertir a pandas para merge geoespacial
    sql_text = f"SELECT {code_col}, {value_col} FROM '{path}'"
    data_table = duckdb.sql(sql_text).pl().to_pandas()

    # fusionar datos tabulares con la geometria del shapefile
    merged_geodata = geo_df.merge(data_table, on=code_col, how="left")
    return merged_geodata


def export_folium_map(
    merged_gdf: Any,
    output_html_path: Union[str, Path] = "mapa.html",
    value_col: str = "valor",
    colormap: str = "Blues",
    tooltip_cols: Optional[List[str]] = None,
    tiles: str = "Esri.WorldGrayCanvas"
) -> Path:
    """Generar mapa interactivo folium exportable a archivo html."""
    _require_folium()
    if tooltip_cols is None:
        tooltip_cols = ["nombre", value_col]

    # filtrar columnas disponibles en el geodataframe para evitar errores en tooltip
    available_tooltips = [col for col in tooltip_cols if col in merged_gdf.columns]

    target_path = Path(output_html_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # renderizar y guardar mapa interactivo con mosaicos de esri para evitar bloqueo 403 de osm
    interactive_map = merged_gdf.explore(
        column=value_col,
        cmap=colormap,
        tooltip=available_tooltips if available_tooltips else None,
        tiles=tiles
    )
    interactive_map.save(str(target_path))
    return target_path


def create_plotly_choropleth(
    merged_gdf: Any,
    code_col: str = "cod",
    value_col: str = "valor",
    hover_name: str = "nombre",
    center_lat: float = 15.5,
    center_lon: float = -90.4,
    zoom: int = 6,
    map_style: str = "carto-positron"
) -> Any:
    """Construir mapa coropletico con plotly express ideal para streamlit y paneles web."""
    px = _require_plotly()
    hover_field = hover_name if hover_name in merged_gdf.columns else None

    # usar choropleth_map segun la version moderna de plotly o choropleth_mapbox como fallback
    if hasattr(px, "choropleth_map"):
        figure = px.choropleth_map(
            merged_gdf,
            geojson=merged_gdf.__geo_interface__,
            locations=code_col,
            featureidkey=f"properties.{code_col}",
            color=value_col,
            hover_name=hover_field,
            center={"lat": center_lat, "lon": center_lon},
            zoom=zoom,
            map_style=map_style
        )
    else:
        figure = px.choropleth_mapbox(
            merged_gdf,
            geojson=merged_gdf.__geo_interface__,
            locations=code_col,
            featureidkey=f"properties.{code_col}",
            color=value_col,
            hover_name=hover_field,
            center={"lat": center_lat, "lon": center_lon},
            zoom=zoom,
            mapbox_style=map_style
        )

    return figure
