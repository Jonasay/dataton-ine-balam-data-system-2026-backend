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

from src.process.relief_3d import (
    build_deckgl_3d_relief_html,
    build_guatemala_relief_scene,
    render_guatemala_with_blender,
)


def _resolve_raw_path(file_path: Union[str, Path]) -> Path:
    """Resolver ruta de archivo en directorio raw buscando coincidencias si es necesario."""
    path = Path(file_path)
    if path.exists():
        return path

    direct_path = RAW_DATA_DIR / path
    if direct_path.exists():
        return direct_path

    # buscar coincidencia por nombre de archivo dentro de subcarpetas en raw
    file_name = path.name
    matches = list(RAW_DATA_DIR.rglob(file_name))
    if matches:
        return matches[0]

    if path.name == "departamentos_gt.geojson":
        from src.core.geo_master import ensure_guatemala_geojson
        return ensure_guatemala_geojson(direct_path)

    return direct_path


def _resolve_processed_path(file_path: Union[str, Path]) -> Path:
    """Resolver ruta de archivo en directorio processed buscando coincidencias si es necesario."""
    path = Path(file_path)
    if path.exists():
        return path

    direct_path = PROCESSED_DATA_DIR / path
    if direct_path.exists():
        return direct_path

    # buscar coincidencia por nombre de archivo dentro de subcarpetas en processed
    file_name = path.name
    matches = list(PROCESSED_DATA_DIR.rglob(file_name))
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
    path = _resolve_processed_path(parquet_path)

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
    path = _resolve_processed_path(parquet_path)

    # identificar columnas existentes en el archivo parquet
    existing_cols = []
    try:
        sample_query = duckdb.sql(f"SELECT * FROM '{path}' LIMIT 0")
        sample_cols = getattr(sample_query, "columns", None)
        if isinstance(sample_cols, list):
            existing_cols = sample_cols
    except Exception:
        existing_cols = []

    # determinar la columna de codigo departamental si no esta presente
    active_code_col = code_col
    if existing_cols and active_code_col not in existing_cols:
        for cand in [
            "depto_codigo", "depto_codigo_norm", "depto_ocu",
            "depto", "departamento", "cod_depto", "codigo_depto"
        ]:
            if cand in existing_cols:
                active_code_col = cand
                break

    # seleccionar directamente o agregar por conteo si no existe columna valor precalculada
    if existing_cols and value_col not in existing_cols:
        sql_text = f"""
            SELECT lpad(cast({active_code_col} as varchar), 2, '0') as cod,
                   count(*) as {value_col}
            FROM '{path}'
            GROUP BY {active_code_col}
        """
    else:
        sql_text = f"SELECT lpad(cast({active_code_col} as varchar), 2, '0') as cod, {value_col} FROM '{path}'"

    data_table = duckdb.sql(sql_text).pl().to_pandas()

    # fusionar datos tabulares con la geometria del shapefile y rellenar valores nulos
    merged_geodata = geo_df.merge(data_table, on="cod", how="left")
    if value_col in merged_geodata.columns:
        merged_geodata[value_col] = merged_geodata[value_col].fillna(0)

    return merged_geodata


def derive_topic_title(parquet_name_or_path: Union[str, Path], fallback_col: str = "valor") -> str:
    """Deducir un titulo descriptivo del tema a partir del nombre del archivo parquet o columna."""
    stem = Path(parquet_name_or_path).stem
    # remover prefijos comunes para obtener el nombre del tema
    clean = stem
    for prefix in ["resumen_", "datos_", "tabla_", "ine_", "gt_", "mapa_"]:
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):]
    words = clean.replace("_", " ").strip()
    if words:
        return words.title()
    return fallback_col.replace("_", " ").title()


def _format_metric_number(value: Any) -> str:
    # formatear valores numericos respetando enteros grandes y tasas decimales
    num = float(value or 0.0)
    if abs(num - round(num)) < 1e-6:
        return f"{int(round(num)):,}"
    return f"{num:,.2f}"


def build_guatemala_sidebar_html(
    merged_gdf: Any,
    value_col: str = "valor",
    name_col: str = "nombre",
    topic_title: Optional[str] = None
) -> str:
    """Construir panel lateral flotante con kpis, ranking de departamentos y boton de centrado."""
    try:
        if not hasattr(merged_gdf, "sort_values") or value_col not in getattr(merged_gdf, "columns", []):
            return ""

        sorted_df = merged_gdf.sort_values(by=value_col, ascending=False)
        active_name_col = name_col if name_col in getattr(merged_gdf, "columns", []) else "nombre"
        series_vals = merged_gdf[value_col].astype(float)
        is_rate_metric = any(
            value_col.startswith(pref)
            for pref in ["tasa_", "pct_", "indice_", "razon_", "inflacion_", "brecha_", "perdida_"]
        )
        total_val = float(series_vals.sum())
        avg_val = float(series_vals.mean())
        primary_kpi_label = "Mediana Nacional" if is_rate_metric else "Total Nacional"
        primary_kpi_val = _format_metric_number(series_vals.median() if is_rate_metric else total_val)
        avg_val_fmt = _format_metric_number(avg_val)

        max_row = sorted_df.iloc[0]
        min_row = sorted_df.iloc[-1]
        max_num = float(max_row[value_col]) if float(max_row[value_col]) > 0 else 1.0
        max_val_fmt = _format_metric_number(max_row[value_col])
        min_val_fmt = _format_metric_number(min_row[value_col])
        display_topic = topic_title or f"Datos de {value_col.capitalize()}"

        items_html = ""
        for idx, (_, row) in enumerate(sorted_df.iterrows(), start=1):
            row_val = float(row[value_col] or 0.0)
            pct = (row_val / max_num) * 100
            val_formatted = _format_metric_number(row_val)
            items_html += f"""
            <div style="display:flex; justify-content:space-between; align-items:center; padding:7px 8px; border-bottom:1px solid #f1f5f9; font-size:12px;">
              <div style="flex:1;">
                <div style="font-weight:600; color:#1e293b;">#{idx} {row.get(active_name_col, 'Dpto')}</div>
                <div style="background:#e2e8f0; border-radius:4px; height:5px; width:100%; margin-top:3px; overflow:hidden;">
                  <div style="background:linear-gradient(90deg, #f59e0b, #ef4444); height:100%; width:{pct:.1f}%;"></div>
                </div>
              </div>
              <div style="margin-left:12px; font-weight:700; color:#0f172a; text-align:right;">
                {val_formatted}
              </div>
            </div>
            """

        sidebar_html = f"""
        <div id="gt-dashboard-panel" style="position:fixed; top:15px; right:15px; width:330px; max-height:calc(100vh - 30px); z-index:9999; background:rgba(255,255,255,0.97); backdrop-filter:blur(10px); border-radius:14px; box-shadow:0 12px 30px -5px rgba(0,0,0,0.2), 0 8px 10px -6px rgba(0,0,0,0.1); font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif; display:flex; flex-direction:column; overflow:hidden; border:1px solid #cbd5e1;">
          <div style="padding:12px 14px; background:linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%); color:white; display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:22px;">🇬🇹</span>
              <div>
                <h3 style="margin:0; font-size:13px; font-weight:800; letter-spacing:-0.2px;">Estadísticas de Guatemala</h3>
                <p style="margin:1px 0 0 0; font-size:10px; opacity:0.85;">Instituto Nacional de Estadística (INE)</p>
                <div style="font-size:11px; font-weight:700; color:#38bdf8; margin-top:3px; background:rgba(56,189,248,0.18); padding:2px 7px; border-radius:4px; display:inline-block; border:1px solid rgba(56,189,248,0.3);">
                  📊 {display_topic}
                </div>
              </div>
            </div>
            <div style="display:flex; align-items:center; gap:6px;">
              <button onclick="centrarMapaGuatemala()" style="background:#0284c7; border:none; color:white; border-radius:6px; cursor:pointer; font-size:11px; font-weight:700; padding:5px 9px; display:inline-flex; align-items:center; gap:3px; box-shadow:0 2px 4px rgba(0,0,0,0.3);" title="Centrar mapa en Guatemala">🎯 Centrar</button>
              <button onclick="var c=document.getElementById('gt-panel-content'); var b=this; if(c.style.display==='none'){{c.style.display='flex'; b.innerText='—';}}else{{c.style.display='none'; b.innerText='+';}}" style="background:rgba(255,255,255,0.2); border:none; color:white; border-radius:6px; cursor:pointer; font-size:14px; font-weight:bold; width:26px; height:26px; display:flex; align-items:center; justify-content:center;">—</button>
            </div>
          </div>
          <div id="gt-panel-content" style="display:flex; flex-direction:column; overflow:hidden;">
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; padding:10px; background:#f8fafc; border-bottom:1px solid #e2e8f0;">
              <div style="background:white; padding:8px 10px; border-radius:8px; border:1px solid #e2e8f0;">
                <div style="font-size:10px; color:#64748b; font-weight:700; text-transform:uppercase;">{primary_kpi_label}</div>
                <div style="font-size:17px; font-weight:800; color:#0f172a; margin-top:2px;">{primary_kpi_val}</div>
              </div>
              <div style="background:white; padding:8px 10px; border-radius:8px; border:1px solid #e2e8f0;">
                <div style="font-size:10px; color:#64748b; font-weight:700; text-transform:uppercase;">Promedio Dpto</div>
                <div style="font-size:17px; font-weight:800; color:#0f172a; margin-top:2px;">{avg_val_fmt}</div>
              </div>
              <div style="background:white; padding:8px 10px; border-radius:8px; border:1px solid #e2e8f0; grid-column:span 2;">
                <div style="display:flex; justify-content:space-between; font-size:11px;">
                  <span>🏆 <b>Mayor:</b> {max_row.get(active_name_col, '')} ({max_val_fmt})</span>
                  <span style="color:#64748b;">📉 <b>Menor:</b> {min_row.get(active_name_col, '')} ({min_val_fmt})</span>
                </div>
              </div>
            </div>
            <div style="padding:8px 12px 4px; font-size:10px; font-weight:800; color:#475569; text-transform:uppercase; letter-spacing:0.5px;">
              Desglose por Departamento
            </div>
            <div style="overflow-y:auto; max-height:calc(100vh - 220px); padding:0 10px 10px;">
              {items_html}
            </div>
          </div>
          <script>
            function centrarMapaGuatemala() {{
              try {{
                for (var k in window) {{
                  try {{
                    if (window[k] && window[k]._leaflet_id && typeof window[k].fitBounds === 'function') {{
                      window[k].fitBounds([[13.73, -92.25], [17.82, -88.22]]);
                      return;
                    }}
                  }} catch(e) {{}}
                }}
                var pDiv = document.querySelector('.plotly-graph-div') || document.querySelector('.js-plotly-plot');
                if (pDiv && typeof Plotly !== 'undefined') {{
                  var relayoutUpdate = {{
                    'map.center.lat': 15.78, 'map.center.lon': -90.23, 'map.zoom': 6.3,
                    'mapbox.center.lat': 15.78, 'mapbox.center.lon': -90.23, 'mapbox.zoom': 6.3
                  }};
                  Plotly.relayout(pDiv, relayoutUpdate);
                  return;
                }}
                if (window.deckInstance && typeof window.centrarMapaGuatemala === 'function') {{
                  window.centrarMapaGuatemala();
                  return;
                }}
              }} catch(err) {{
                console.error('Error al centrar mapa:', err);
              }}
            }}
          </script>
        </div>
        """
        return sidebar_html
    except Exception:
        return ""


def export_folium_map(
    merged_gdf: Any,
    output_html_path: Union[str, Path] = "mapa.html",
    value_col: str = "valor",
    colormap: str = "YlOrRd",
    tooltip_cols: Optional[List[str]] = None,
    tiles: str = "Esri.WorldGrayCanvas",
    topic_title: Optional[str] = None
) -> Path:
    """Generar mapa interactivo folium exportable a archivo html con panel lateral y vista de guatemala."""
    folium = _require_folium()
    if tooltip_cols is None:
        tooltip_cols = ["nombre", value_col]

    available_tooltips = [col for col in tooltip_cols if col in getattr(merged_gdf, "columns", [])]
    target_path = Path(output_html_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # renderizar mapa con clasificacion natural breaks y bordes oscuros nitidos
    scheme_param = "NaturalBreaks" if hasattr(merged_gdf, "__len__") and len(merged_gdf) >= 6 else None
    interactive_map = merged_gdf.explore(
        column=value_col,
        cmap=colormap,
        scheme=scheme_param,
        k=6 if scheme_param else None,
        style_kwds={"color": "#0f172a", "weight": 2.2, "fillOpacity": 0.88},
        highlight_kwds={"fillColor": "#38bdf8", "fillOpacity": 0.95, "weight": 3.2, "color": "#0f172a"},
        tooltip=available_tooltips if available_tooltips else None,
        tiles=tiles
    )

    # agregar capas conmutables incluyendo relieve sombreado 3d y satelital
    try:
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}",
            attr="Esri World Shaded Relief",
            name="Relieve 3D (Sombreado)",
            overlay=False
        ).add_to(interactive_map)

        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri World Imagery",
            name="Satelital Realista",
            overlay=False
        ).add_to(interactive_map)

        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
            attr="Esri World Street Map",
            name="Calles y Ciudades",
            overlay=False
        ).add_to(interactive_map)

        folium.LayerControl(position="topleft").add_to(interactive_map)
    except Exception:
        pass

    # encuadrar exactamente en la republica de guatemala
    try:
        interactive_map.fit_bounds([[13.73, -92.25], [17.82, -88.22]])
    except Exception:
        pass

    # inyectar panel lateral con estadisticas de guatemala
    sidebar_markup = build_guatemala_sidebar_html(
        merged_gdf, value_col=value_col, topic_title=topic_title
    )
    if sidebar_markup:
        try:
            interactive_map.get_root().html.add_child(folium.Element(sidebar_markup))
        except Exception:
            pass

    interactive_map.save(str(target_path))
    return target_path


def create_plotly_choropleth(
    merged_gdf: Any,
    code_col: str = "cod",
    value_col: str = "valor",
    hover_name: str = "nombre",
    center_lat: float = 15.78,
    center_lon: float = -90.23,
    zoom: float = 6.3,
    map_style: str = "white-bg",
    color_scale: str = "Turbo",
    pitch: int = 40,
    bearing: int = 0,
    topic_title: Optional[str] = None
) -> Any:
    """Construir mapa coropletico con plotly express con vista 3D y encuadre en Guatemala."""
    px = _require_plotly()
    cols = getattr(merged_gdf, "columns", [])
    hover_field = hover_name if hover_name in cols else ("nombre" if "nombre" in cols else None)

    # normalizar features asegurando que tengan identificador explicito para vincular con las ubicaciones
    geo_data = getattr(merged_gdf, "__geo_interface__", None)
    if isinstance(geo_data, dict) and "features" in geo_data:
        for feat in geo_data["features"]:
            if isinstance(feat, dict):
                props = feat.get("properties", {})
                if code_col in props:
                    feat["id"] = str(props[code_col])

    # capa base de esri confiable sin problemas de bloqueo 403 o requerimientos de token de carto
    esri_layer = {
        "below": "traces",
        "sourcetype": "raster",
        "source": [
            "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        ]
    }

    # usar choropleth_map segun la version moderna de plotly o choropleth_mapbox como fallback
    if hasattr(px, "choropleth_map"):
        figure = px.choropleth_map(
            merged_gdf,
            geojson=geo_data,
            locations=code_col,
            featureidkey=f"properties.{code_col}",
            color=value_col,
            hover_name=hover_field,
            color_continuous_scale=color_scale,
            center={"lat": center_lat, "lon": center_lon},
            zoom=zoom,
            map_style=map_style
        )
        try:
            figure.update_layout(map=dict(pitch=pitch, bearing=bearing, layers=[esri_layer]))
        except Exception:
            pass
    else:
        figure = px.choropleth_mapbox(
            merged_gdf,
            geojson=geo_data,
            locations=code_col,
            featureidkey=f"properties.{code_col}",
            color=value_col,
            hover_name=hover_field,
            color_continuous_scale=color_scale,
            center={"lat": center_lat, "lon": center_lon},
            zoom=zoom,
            mapbox_style=map_style
        )
        try:
            figure.update_layout(mapbox=dict(pitch=pitch, bearing=bearing, layers=[esri_layer]))
        except Exception:
            pass

    # remarcar bordes de cada departamento con trazo oscuro nitido
    try:
        figure.update_traces(
            marker_line_width=1.8,
            marker_line_color="#0f172a",
            marker_opacity=0.88
        )
    except Exception:
        pass

    # ajustar margenes y titulo descriptivo
    display_title = (
        f"🇬🇹 Estadísticas de Guatemala (INE) - {topic_title}"
        if topic_title
        else f"🇬🇹 Estadísticas Oficiales de Guatemala (INE) - {value_col.capitalize()}"
    )
    figure.update_layout(
        margin={"r": 0, "t": 45, "l": 0, "b": 0},
        title={"text": display_title, "x": 0.05, "y": 0.96}
    )
    return figure


