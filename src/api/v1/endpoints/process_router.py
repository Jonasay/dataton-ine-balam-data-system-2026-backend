from __future__ import annotations

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

from src.core.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from src.process.process import (
    aggregate_parquet,
    build_deckgl_3d_relief_html,
    build_guatemala_relief_scene,
    build_guatemala_sidebar_html,
    create_plotly_choropleth,
    derive_topic_title,
    excel_to_parquet,
    export_folium_map,
    load_geodata,
    merge_geo_with_parquet,
    read_excel_sheets,
    render_guatemala_with_blender,
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
    ruta_geo: str = Query(default="geo/departamentos_gt.geojson", description="Ruta del archivo shapefile o geojson dentro de data/raw"),
    ruta_parquet: str = Query(..., description="Ruta del archivo parquet dentro de data/processed"),
    columna_codigo_geo: str = Query(default="COD_COLUMNA", description="Columna codigo en capa espacial"),
    columna_codigo_parquet: str = Query(default="cod", description="Columna codigo en parquet"),
    columna_valor: str = Query(default="valor", description="Columna cuantitativa a graficar"),
    columna_nombre: str = Query(default="nombre", description="Columna para tooltip del mapa"),
    titulo_estadistica: Optional[str] = Query(default=None, description="Titulo o tema descriptivo de la estadistica (si se omite, se deduce del nombre del parquet)"),
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

        topic_title = titulo_estadistica or derive_topic_title(ruta_parquet, columna_valor)
        parquet_stem = Path(ruta_parquet).stem
        map_filename = f"mapa_{parquet_stem}.html"
        output_file = PROCESSED_DATA_DIR / map_filename

        saved_html = export_folium_map(
            merged_gdf=merged_gdf,
            output_html_path=output_file,
            value_col=columna_valor,
            colormap=esquema_color,
            tooltip_cols=[columna_nombre, columna_valor],
            tiles=capa_base,
            topic_title=topic_title
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
    ruta_geo: str = Query(default="geo/departamentos_gt.geojson", description="Ruta del archivo shapefile o geojson dentro de data/raw"),
    ruta_parquet: str = Query(..., description="Ruta del archivo parquet dentro de data/processed"),
    columna_codigo_geo: str = Query(default="COD_COLUMNA", description="Columna codigo en capa espacial"),
    columna_codigo_parquet: str = Query(default="cod", description="Columna codigo en parquet"),
    columna_valor: str = Query(default="valor", description="Columna cuantitativa a graficar"),
    columna_nombre: str = Query(default="nombre", description="Columna para hover"),
    titulo_estadistica: Optional[str] = Query(default=None, description="Titulo o tema descriptivo de la estadistica (si se omite, se deduce del nombre del parquet)"),
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

        topic_title = titulo_estadistica or derive_topic_title(ruta_parquet, columna_valor)

        fig = create_plotly_choropleth(
            merged_gdf=merged_gdf,
            code_col="cod",
            value_col=columna_valor,
            hover_name=columna_nombre,
            topic_title=topic_title
        )

        parquet_stem = Path(ruta_parquet).stem
        map_filename = f"mapa_plotly_{parquet_stem}.html"
        output_file = PROCESSED_DATA_DIR / map_filename

        if formato.lower() == "html":
            html_markup = fig.to_html(include_plotlyjs="cdn")
            sidebar_markup = build_guatemala_sidebar_html(
                merged_gdf,
                value_col=columna_valor,
                name_col=columna_nombre,
                topic_title=topic_title
            )
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


# mapa 3d iteractivo con deck.gl
@router.get("/mapa-3d-relieve", summary="Mapa 3D interactivo con relieve segun datos", response_class=HTMLResponse)
def get_3d_relief_map(
    ruta_geo: str = Query(default="geo/departamentos_gt.geojson", description="Ruta del shapefile o geojson en data/raw"),
    ruta_parquet: str = Query(..., description="Ruta del parquet en data/processed"),
    columna_codigo_geo: str = Query(default="COD_COLUMNA"),
    columna_codigo_parquet: str = Query(default="cod"),
    columna_valor: str = Query(default="valor"),
    columna_nombre: str = Query(default="nombre"),
    titulo_estadistica: Optional[str] = Query(default=None, description="Titulo o tema descriptivo de la estadistica"),
    estilo_color: str = Query(default="multicolor", description="Estilo de color: multicolor (color unico por departamento), negro (relieve negro de alto contraste) o calor (gradiente termico)"),
    altura_max_m: float = Query(default=60000.0, ge=1000, description="Altura maxima del relieve en metros del modelo 3d"),
    descargar: bool = Query(default=False),
):
    """Construir mapa interactivo 3D en el navegador con relieve volumetrico en deck.gl."""
    try:
        geo_data = load_geodata(ruta_geo, target_crs=4326, code_col=columna_codigo_geo)
        merged_gdf = merge_geo_with_parquet(
            geo_df=geo_data, parquet_path=ruta_parquet,
            code_col=columna_codigo_parquet, value_col=columna_valor
        )
        topic_title = titulo_estadistica or derive_topic_title(ruta_parquet, columna_valor)
        html = build_deckgl_3d_relief_html(
            merged_gdf,
            value_col=columna_valor,
            name_col=columna_nombre,
            code_col="cod",
            topic_title=topic_title,
            color_mode=estilo_color,
            max_elevation_m=altura_max_m
        )
        stem = Path(ruta_parquet).stem
        disposition = "attachment" if descargar else "inline"
        return HTMLResponse(content=html, headers={
            "Content-Disposition": f'{disposition}; filename="mapa_3d_{stem}.html"'
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error al generar mapa 3d: {exc}")


# modelo 3d imprimible (stl o glb con camara incluida)
@router.get("/modelo-3d-impresion", summary="Generar modelo 3D imprimible o para Blender")
def get_printable_3d_model(
    ruta_geo: str = Query(default="geo/departamentos_gt.geojson", description="Ruta del shapefile o geojson en data/raw"),
    ruta_parquet: str = Query(..., description="Ruta del parquet en data/processed"),
    columna_codigo_geo: str = Query(default="COD_COLUMNA"),
    columna_codigo_parquet: str = Query(default="cod"),
    columna_valor: str = Query(default="valor"),
    columna_nombre: str = Query(default="nombre"),
    formato: str = Query(default="glb", description="glb = recomendado para blender (departamentos separados y coloreados); stl = impresion monolitica; zip = pack de STLs individuales separados; obj = wavefront con materiales"),
    estilo_color: str = Query(default="multicolor", description="multicolor = un color por departamento; negro = relieve negro; calor = gradiente"),
    ancho_mm: float = Query(default=150.0, ge=40.0, le=500.0, description="Ancho del modelo impreso en milimetros"),
    altura_max_mm: float = Query(default=60.0, ge=5.0, le=200.0, description="Relieve maximo del departamento con mayor valor"),
    grosor_base_mm: float = Query(default=0.6, ge=0.0, le=20.0, description="Grosor de la base en mm (0.6 mm es super delgada, 0 para sin base)"),
    forma_base: str = Query(default="silueta", description="silueta = contorno exacto de Guatemala; caja = rectangular; ninguna = sin base"),
):
    """Generar archivo 3D de Guatemala con departamentos separados, colores y base delgada de silueta."""
    try:
        import trimesh
        import zipfile

        geo_data = load_geodata(ruta_geo, target_crs=4326, code_col=columna_codigo_geo)
        merged_gdf = merge_geo_with_parquet(
            geo_df=geo_data, parquet_path=ruta_parquet,
            code_col=columna_codigo_parquet, value_col=columna_valor
        )

        scene = build_guatemala_relief_scene(
            merged_gdf,
            value_col=columna_valor,
            code_col=columna_codigo_parquet,
            name_col=columna_nombre,
            target_width_mm=ancho_mm,
            base_mm=grosor_base_mm,
            forma_base=forma_base,
            max_relief_mm=altura_max_mm,
            add_camera=(formato.lower() == "glb"),
            color_mode=estilo_color
        )

        stem = Path(ruta_parquet).stem
        fmt = formato.lower().strip()

        # caso 1: zip con stls individuales por departamento
        if fmt == "zip":
            output_file = PROCESSED_DATA_DIR / f"modelos_stl_{stem}.zip"
            with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zf:
                for geom_name, geom in scene.geometry.items():
                    stl_bytes = geom.export(file_type="stl")
                    zf.writestr(f"{geom_name}.stl", stl_bytes)
            return FileResponse(str(output_file), media_type="application/zip", filename=output_file.name)

        # caso 2: stl monolitico unido
        if fmt == "stl":
            output_file = PROCESSED_DATA_DIR / f"modelo_3d_{stem}.stl"
            solid = trimesh.util.concatenate(list(scene.geometry.values()))
            solid.export(str(output_file))
            return FileResponse(str(output_file), media_type="model/stl", filename=output_file.name)

        # caso 3: obj con mallas separadas
        if fmt == "obj":
            output_file = PROCESSED_DATA_DIR / f"modelo_3d_{stem}.obj"
            obj_data = scene.export(file_type="obj")
            output_file.write_text(obj_data, encoding="utf-8")
            return FileResponse(str(output_file), media_type="text/plain", filename=output_file.name)

        # caso 4 por defecto: glb con departamentos separados y coloreados para blender
        output_file = PROCESSED_DATA_DIR / f"modelo_3d_{stem}.glb"
        scene.export(str(output_file))
        return FileResponse(str(output_file), media_type="model/gltf-binary", filename=output_file.name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error al generar modelo 3d: {exc}")


# render 3d hiperrealista con blender
@router.get("/render-3d-blender", summary="Renderizar modelo 3D con Blender headless a imagen PNG")
def get_blender_3d_render(
    ruta_geo: str = Query(default="geo/departamentos_gt.geojson", description="Ruta del shapefile o geojson en data/raw"),
    ruta_parquet: str = Query(..., description="Ruta del parquet en data/processed"),
    columna_codigo_geo: str = Query(default="COD_COLUMNA"),
    columna_codigo_parquet: str = Query(default="cod"),
    columna_valor: str = Query(default="valor"),
    columna_nombre: str = Query(default="nombre"),
    estilo_color: str = Query(default="multicolor", description="Estilo de color: multicolor (un color por departamento), negro (relieve negro de alto contraste) o azul (azul petroleo)"),
    grosor_base_mm: float = Query(default=0.6, ge=0.0, le=20.0, description="Grosor de la base en mm"),
    ancho_px: int = Query(default=1280, ge=320, le=3840, description="Ancho de la imagen renderizada en pixeles"),
    alto_px: int = Query(default=720, ge=240, le=2160, description="Alto de la imagen renderizada en pixeles"),
    descargar: bool = Query(default=False, description="Descargar el archivo PNG en lugar de visualizarlo inline"),
):
    """Renderizar modelo de relieve 3D de Guatemala en Blender con iluminacion de estudio profesional."""
    try:
        geo_data = load_geodata(ruta_geo, target_crs=4326, code_col=columna_codigo_geo)
        merged_gdf = merge_geo_with_parquet(
            geo_df=geo_data, parquet_path=ruta_parquet,
            code_col=columna_codigo_parquet, value_col=columna_valor
        )

        parquet_stem = Path(ruta_parquet).stem
        glb_path = PROCESSED_DATA_DIR / f"modelo_3d_{parquet_stem}.glb"
        png_path = PROCESSED_DATA_DIR / f"render_3d_{parquet_stem}.png"

        # generar escena 3d y exportar a glb con silueta de guatemala
        scene = build_guatemala_relief_scene(
            merged_gdf,
            value_col=columna_valor,
            code_col=columna_codigo_parquet,
            name_col=columna_nombre,
            target_width_mm=150.0,
            base_mm=grosor_base_mm,
            forma_base="silueta",
            max_relief_mm=60.0,
            add_camera=True,
            color_mode=estilo_color
        )
        scene.export(str(glb_path))

        # renderizar usando blender local o docker
        render_guatemala_with_blender(
            glb_path=glb_path,
            output_png_path=png_path,
            width=ancho_px,
            height=alto_px,
            color_mode=estilo_color
        )

        disposition = "attachment" if descargar else "inline"
        headers = {
            "Content-Disposition": f'{disposition}; filename="render_3d_{parquet_stem}.png"'
        }
        return FileResponse(str(png_path), media_type="image/png", headers=headers)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error al renderizar con blender: {exc}")