from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from src.core.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from src.process.process import (
    aggregate_parquet,
    build_guatemala_sidebar_html,
    create_plotly_choropleth,
    excel_to_parquet,
    export_folium_map,
    load_geodata,
    merge_geo_with_parquet,
    read_excel_sheets
)
from src.schemas.process import (
    ExcelToParquetRequest,
    GeoMapRequest,
    ParquetAggregateRequest
)

router = APIRouter(
    prefix="/proceso",
    tags=["Procesamiento - Analitica y Mapas"]
)


# inspeccionar hojas de calculo de un archivo excel y obtener vista previa
@router.get("/hojas-excel", summary="Inspeccionar hojas de un archivo excel")
def get_excel_sheets(
    ruta_excel: Optional[str] = Query(default=None, description="Ruta relativa o nombre del archivo excel dentro de data/raw"),
    slug: Optional[str] = Query(default=None, description="Slug del dataset en ine para previsualizar automaticamente sin ruta local"),
    limite: int = Query(default=10, ge=1, le=1000, description="Numero de filas para vista previa"),
    hoja_id: int = Query(default=1, ge=0, description="Indice o identificador de la hoja a previsualizar"),
):
    """Inspeccionar nombres de hojas y previsualizar las primeras filas con polars."""
    try:
        if slug is not None:
            from src.api.v1.endpoints.ine_router import preview_dataset_data
            return preview_dataset_data(slug=slug, hoja_id=hoja_id, limite=limite)

        if not ruta_excel:
            raise HTTPException(status_code=400, detail="debe proporcionar ruta_excel o slug")

        workbook_dict = read_excel_sheets(ruta_excel, sheet_id=0)
        sheet_names = list(workbook_dict.keys()) if isinstance(workbook_dict, dict) else []

        # previsualizar la hoja seleccionada
        sheet_df = read_excel_sheets(ruta_excel, sheet_id=hoja_id)
        preview_rows = sheet_df.head(limite).to_dicts()
        columns_list = sheet_df.columns

        return {
            "archivo": ruta_excel,
            "hojas": sheet_names,
            "hoja_actual": hoja_id,
            "columnas": columns_list,
            "filas_muestra": preview_rows
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error al leer archivo excel: {exc}")


# convertir una hoja excel a formato parquet con compresion zstd
@router.post("/convertir", summary="Convertir hoja de excel a parquet")
@router.post("/excel-a-parquet", summary="Convertir hoja de excel a parquet (alias)", include_in_schema=False)
def post_excel_to_parquet(body: ExcelToParquetRequest):
    """Convertir archivo tabular de excel a parquet con compresion zstd."""
    try:
        target_parquet_name = body.ruta_salida_parquet
        if not target_parquet_name:
            base_name = Path(body.ruta_excel).stem
            target_parquet_name = f"{base_name}.parquet"

        output_path = excel_to_parquet(
            excel_path=body.ruta_excel,
            output_parquet_path=target_parquet_name,
            sheet_id=body.hoja_id,
            compression=body.compresion
        )

        return {
            "mensaje": "archivo parquet generado exitosamente",
            "origen_excel": body.ruta_excel,
            "destino_parquet": str(output_path),
            "nombre_archivo": output_path.name,
            "tamano_bytes": output_path.stat().st_size
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error al convertir a parquet: {exc}")


# consultar resumen y agregaciones de registros sin escribir sql
@router.get("/resumen", summary="Consultar resumen y agrupaciones de parquet")
def get_parquet_summary(
    ruta_parquet: str = Query(..., description="Ruta o nombre del archivo parquet en data/processed"),
    agrupar_por: str = Query(..., description="Nombre de la columna para agrupar (ej. depto_ocu, tipo_veh)"),
    columna_filtro: Optional[str] = Query(default=None, description="Columna opcional de filtrado (ej. ano_ocu)"),
    valor_filtro: Optional[str] = Query(default=None, description="Valor del filtro opcional"),
    limite: int = Query(default=10, ge=1, le=10000, description="Cantidad maxima de resultados"),
):
    """Calcular conteos y estadisticas agrupadas sobre parquet automaticamente sin requerir sentencias sql."""
    try:
        # convertir valor numerico si aplica
        parsed_filter_val = valor_filtro
        if valor_filtro is not None:
            if valor_filtro.isdigit():
                parsed_filter_val = int(valor_filtro)

        summary_data = aggregate_parquet(
            parquet_path=ruta_parquet,
            group_by=agrupar_por,
            filter_col=columna_filtro,
            filter_val=parsed_filter_val,
            limit=limite
        )
        return summary_data
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error al generar resumen de parquet: {exc}")


@router.post("/resumen", summary="Consultar resumen y agrupaciones con cuerpo json")
def post_parquet_summary(body: ParquetAggregateRequest):
    """Calcular conteos y estadisticas agrupadas enviando parametros en formato json."""
    try:
        summary_data = aggregate_parquet(
            parquet_path=body.ruta_parquet,
            group_by=body.agrupar_por,
            filter_col=body.columna_filtro,
            filter_val=body.valor_filtro,
            limit=body.limite
        )
        return summary_data
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error al generar resumen de parquet: {exc}")


# generar y visualizar mapa interactivo en html con folium
@router.get("/mapa-html", summary="Generar y visualizar mapa interactivo folium", response_class=HTMLResponse)
def get_interactive_folium_map(
    ruta_geo: str = Query(..., description="Ruta del archivo shapefile o geojson dentro de data/raw"),
    ruta_parquet: str = Query(..., description="Ruta del archivo parquet dentro de data/processed"),
    columna_codigo_geo: str = Query(default="COD_COLUMNA", description="Columna codigo en capa espacial"),
    columna_codigo_parquet: str = Query(default="cod", description="Columna codigo en parquet"),
    columna_valor: str = Query(default="valor", description="Columna cuantitativa a graficar"),
    columna_nombre: str = Query(default="nombre", description="Columna para tooltip del mapa"),
    esquema_color: str = Query(default="YlOrRd", description="Colores para coropleta (ej. YlOrRd, Turbo, Viridis, Blues)"),
    capa_base: str = Query(default="Esri.WorldGrayCanvas", description="Proveedor de mosaicos base (ej. Esri.WorldGrayCanvas, Esri.WorldStreetMap)"),
    descargar: bool = Query(default=False, description="Descargar el archivo directamente con el nombre del parquet en lugar de solo visualizarlo"),
):
    """Construir mapa interactivo con folium y retornarlo como pagina html con el nombre del parquet."""
    try:
        # cargar capa espacial y unir con datos analiticos de parquet
        geo_data = load_geodata(ruta_geo, target_crs=4326, code_col=columna_codigo_geo)
        merged_gdf = merge_geo_with_parquet(
            geo_df=geo_data,
            parquet_path=ruta_parquet,
            code_col=columna_codigo_parquet,
            value_col=columna_valor
        )

        parquet_stem = Path(ruta_parquet).stem
        map_filename = f"mapa_{parquet_stem}.html"
        output_file = PROCESSED_DATA_DIR / map_filename

        saved_html = export_folium_map(
            merged_gdf=merged_gdf,
            output_html_path=output_file,
            value_col=columna_valor,
            colormap=esquema_color,
            tooltip_cols=[columna_nombre, columna_valor],
            tiles=capa_base
        )

        html_content = saved_html.read_text(encoding="utf-8")
        disposition = "attachment" if descargar else "inline"
        headers = {
            "Content-Disposition": f'{disposition}; filename="{map_filename}"'
        }
        return HTMLResponse(content=html_content, headers=headers)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error al generar mapa folium: {exc}")


# generar mapa coropletico con plotly para paneles web o streamlit
@router.get("/mapa-plotly", summary="Generar mapa coropletico con plotly")
def get_plotly_choropleth_map(
    ruta_geo: str = Query(..., description="Ruta del archivo shapefile o geojson dentro de data/raw"),
    ruta_parquet: str = Query(..., description="Ruta del archivo parquet dentro de data/processed"),
    columna_codigo_geo: str = Query(default="COD_COLUMNA", description="Columna codigo en capa espacial"),
    columna_codigo_parquet: str = Query(default="cod", description="Columna codigo en parquet"),
    columna_valor: str = Query(default="valor", description="Columna cuantitativa a graficar"),
    columna_nombre: str = Query(default="nombre", description="Columna para hover"),
    formato: str = Query(default="html", description="Formato de respuesta: html para visor web o json para react/streamlit"),
    descargar: bool = Query(default=False, description="Descargar el archivo html con el nombre del parquet en lugar de solo visualizarlo"),
):
    """Construir mapa coropletico en plotly express devolviendo html interactivo o estructura json."""
    try:
        # cargar capa espacial y unir con datos analiticos de parquet
        geo_data = load_geodata(ruta_geo, target_crs=4326, code_col=columna_codigo_geo)
        merged_gdf = merge_geo_with_parquet(
            geo_df=geo_data,
            parquet_path=ruta_parquet,
            code_col=columna_codigo_parquet,
            value_col=columna_valor
        )

        fig = create_plotly_choropleth(
            merged_gdf=merged_gdf,
            code_col="cod",
            value_col=columna_valor,
            hover_name=columna_nombre
        )

        parquet_stem = Path(ruta_parquet).stem
        map_filename = f"mapa_plotly_{parquet_stem}.html"
        output_file = PROCESSED_DATA_DIR / map_filename

        if formato.lower() == "html":
            html_markup = fig.to_html(include_plotlyjs="cdn")
            sidebar_markup = build_guatemala_sidebar_html(merged_gdf, value_col=columna_valor, name_col=columna_nombre)
            if sidebar_markup:
                if "</body>" in html_markup:
                    html_markup = html_markup.replace("</body>", f"{sidebar_markup}</body>")
                else:
                    html_markup += sidebar_markup

            output_file.write_text(html_markup, encoding="utf-8")
            disposition = "attachment" if descargar else "inline"
            headers = {
                "Content-Disposition": f'{disposition}; filename="{map_filename}"'
            }
            return HTMLResponse(content=html_markup, headers=headers)

        return JSONResponse(content={
            **fig.to_dict(),
            "archivo_generado": map_filename
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error al generar mapa plotly: {exc}")
