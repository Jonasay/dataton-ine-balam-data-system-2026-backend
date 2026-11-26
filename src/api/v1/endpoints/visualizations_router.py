from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from src.core.config import PROCESSED_DATA_DIR
from src.analysis.visualizations import (
    INDICATORS_CATALOG,
    build_3d_cost_of_living_trajectory_chart,
    build_3d_demographic_trajectory_chart,
    build_3d_multidimensional_scatter_chart,
    build_3d_pca_clusters_chart,
    build_correlation_heatmap_chart,
    build_cost_of_living_forecast_chart,
    build_demographic_growth_lines_chart,
    build_demographic_structure_stacked_bar_chart,
    build_department_radar_chart,
    build_department_ranking_bar_chart,
    build_ipc_trends_chart,
    build_municipal_ranking_bar_chart,
    build_outliers_boxplot_chart,
    build_pie_distribution_chart,
    build_returnees_composition_bar_chart,
    get_or_build_chart,
    load_enriched_geo_dataframe,
)
from src.process.process import (
    build_guatemala_sidebar_html,
    create_plotly_choropleth,
    export_folium_map,
)
from src.process.relief_3d import (
    build_deckgl_3d_relief_html,
    build_guatemala_relief_scene,
    render_guatemala_with_blender,
)
from src.schemas.visualizations import VisualizationCatalogResponse

router = APIRouter(
    prefix="/visualizaciones",
    tags=["Visualizaciones Interactivas, 3D, Mapas y Blender"]
)

# catalogo estructurado de visualizaciones disponibles para el frontend
VISUALIZATION_CATALOG_ITEMS: List[Dict[str, Any]] = [
    {
        "id_visualizacion": "3d_trayectoria_demografica",
        "titulo": "Trayectoria Demográfica 3D Animada (2015–2030)",
        "categoria": "Gráficas 3D y Movimiento",
        "tipo_grafica": "scatter_3d_animated",
        "descripcion": "Movimiento temporal de los 22 departamentos en el espacio 3D de dependencia, masculinidad y juventud.",
        "soporta_3d": True,
        "soporta_animacion": True,
        "endpoint_json": "/api/v1/visualizaciones/3d/trayectoria-demografica?formato=json",
        "endpoint_html": "/api/v1/visualizaciones/3d/trayectoria-demografica",
        "parametros_principales": ["color_por", "formato"],
    },
    {
        "id_visualizacion": "3d_clusters_pca",
        "titulo": "Espacio 3D de Componentes Principales (PCA) y Conglomerados",
        "categoria": "Gráficas 3D y Movimiento",
        "tipo_grafica": "scatter_3d",
        "descripcion": "Proyección ortogonal 3D (PC1, PC2, PC3 = 80% varianza) con centroides K-Means y vulnerabilidad IVST.",
        "soporta_3d": True,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/3d/clusters-pca?formato=json",
        "endpoint_html": "/api/v1/visualizaciones/3d/clusters-pca",
        "parametros_principales": ["formato"],
    },
    {
        "id_visualizacion": "3d_riesgo_multidimensional",
        "titulo": "Cubo 3D Personalizable de Indicadores",
        "categoria": "Gráficas 3D y Movimiento",
        "tipo_grafica": "scatter_3d",
        "descripcion": "Dispersión 3D interactiva seleccionando cualquier terna de indicadores socioeconómicos.",
        "soporta_3d": True,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/3d/riesgo-multidimensional?formato=json",
        "endpoint_html": "/api/v1/visualizaciones/3d/riesgo-multidimensional",
        "parametros_principales": ["eje_x", "eje_y", "eje_z", "color_por", "tamano_por"],
    },
    {
        "id_visualizacion": "3d_trayectoria_costo_vida",
        "titulo": "Trayectoria 3D Animada de Canasta Básica (2024–2026)",
        "categoria": "Gráficas 3D y Movimiento",
        "tipo_grafica": "scatter_3d_trajectory",
        "descripcion": "Movimiento mensual de la CBA Urbana vs Rural y su brecha monetaria en 34 meses observados.",
        "soporta_3d": True,
        "soporta_animacion": True,
        "endpoint_json": "/api/v1/visualizaciones/3d/trayectoria-costo-vida?formato=json",
        "endpoint_html": "/api/v1/visualizaciones/3d/trayectoria-costo-vida",
        "parametros_principales": ["formato"],
    },
    {
        "id_visualizacion": "barras_ranking_departamental",
        "titulo": "Ranking Departamental Comparativo",
        "categoria": "Barras y Rankings",
        "tipo_grafica": "bar",
        "descripcion": "Barras interactivas por departamento con promedio nacional para cualquier indicador.",
        "soporta_3d": False,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/barras/ranking-departamental?formato=json",
        "endpoint_html": "/api/v1/visualizaciones/barras/ranking-departamental",
        "parametros_principales": ["indicador", "top_n", "orden", "orientacion"],
    },
    {
        "id_visualizacion": "barras_ranking_municipal",
        "titulo": "Ranking Municipal de Puntos Críticos (340 Municipios)",
        "categoria": "Barras y Rankings",
        "tipo_grafica": "bar_municipal",
        "descripcion": "Desagregación local municipal filtrable por departamento.",
        "soporta_3d": False,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/barras/ranking-municipal?formato=json",
        "endpoint_html": "/api/v1/visualizaciones/barras/ranking-municipal",
        "parametros_principales": ["indicador", "depto_codigo", "top_n"],
    },
    {
        "id_visualizacion": "barras_estructura_demografica",
        "titulo": "Estructura Etaria Poblacional Apilada",
        "categoria": "Barras y Rankings",
        "tipo_grafica": "stacked_bar",
        "descripcion": "Barras apiladas 100% de población menor de 15, productiva 15-64 y 65+ por departamento.",
        "soporta_3d": False,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/barras/estructura-demografica?formato=json",
        "endpoint_html": "/api/v1/visualizaciones/barras/estructura-demografica",
        "parametros_principales": ["formato"],
    },
    {
        "id_visualizacion": "barras_composicion_retornados",
        "titulo": "Composición de Población Migrante Retornada",
        "categoria": "Barras y Rankings",
        "tipo_grafica": "grouped_bar",
        "descripcion": "Comparación de menores de edad, adultos y mujeres retornadas por departamento.",
        "soporta_3d": False,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/barras/composicion-retornados?formato=json",
        "endpoint_html": "/api/v1/visualizaciones/barras/composicion-retornados",
        "parametros_principales": ["top_n"],
    },
    {
        "id_visualizacion": "pastel_distribucion",
        "titulo": "Gráficas de Pastel, Donas y Jerarquía Sunburst",
        "categoria": "Pastel y Proporciones",
        "tipo_grafica": "pie_donut_sunburst",
        "descripcion": "Proporciones por clúster, niñez migrante, paridad de género universitaria, víctimas viales y jerarquía territorial.",
        "soporta_3d": False,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/pastel/distribucion?tipo=clusters&formato=json",
        "endpoint_html": "/api/v1/visualizaciones/pastel/distribucion?tipo=clusters",
        "parametros_principales": ["tipo", "depto_codigo", "metrica"],
    },
    {
        "id_visualizacion": "tendencia_costo_vida",
        "titulo": "Evolución y Pronóstico de Canasta Básica (CBA)",
        "categoria": "Tendencias y Estadística",
        "tipo_grafica": "line_forecast",
        "descripcion": "Series observadas urbana y rural con proyección econométrica MCO a 12 meses.",
        "soporta_3d": False,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/tendencias/costo-vida?formato=json",
        "endpoint_html": "/api/v1/visualizaciones/tendencias/costo-vida",
        "parametros_principales": ["formato"],
    },
    {
        "id_visualizacion": "tendencia_ipc",
        "titulo": "Tendencias del IPC por Región, Divisiones y Poder Adquisitivo",
        "categoria": "Tendencias y Estadística",
        "tipo_grafica": "line",
        "descripcion": "Evolución mensual de inflación regional SEGEPLAN, 13 divisiones CCIF y pérdida del quetzal.",
        "soporta_3d": False,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/tendencias/ipc?vista=regiones&formato=json",
        "endpoint_html": "/api/v1/visualizaciones/tendencias/ipc?vista=regiones",
        "parametros_principales": ["vista"],
    },
    {
        "id_visualizacion": "tendencia_crecimiento_demografico",
        "titulo": "Curvas de Crecimiento Demográfico Departamental (2015–2030)",
        "categoria": "Tendencias y Estadística",
        "tipo_grafica": "line",
        "descripcion": "Evolución poblacional proyectada de los departamentos con mayor peso demográfico.",
        "soporta_3d": False,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/tendencias/crecimiento-demografico?top_n=8&formato=json",
        "endpoint_html": "/api/v1/visualizaciones/tendencias/crecimiento-demografico?top_n=8",
        "parametros_principales": ["top_n", "formato"],
    },
    {
        "id_visualizacion": "correlaciones_heatmap",
        "titulo": "Matriz de Correlaciones Anotada (Pearson / Spearman)",
        "categoria": "Tendencias y Estadística",
        "tipo_grafica": "heatmap",
        "descripcion": "Mapa de calor interactivo con coeficientes cruzados entre los principales indicadores.",
        "soporta_3d": False,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/correlaciones/heatmap?formato=json",
        "endpoint_html": "/api/v1/visualizaciones/correlaciones/heatmap",
        "parametros_principales": ["metodo"],
    },
    {
        "id_visualizacion": "outliers_boxplot",
        "titulo": "Detección de Valores Atípicos Territoriales (Z-Score)",
        "categoria": "Tendencias y Estadística",
        "tipo_grafica": "boxplot",
        "descripcion": "Diagramas de caja estandarizados destacando anomalías territoriales extremas.",
        "soporta_3d": False,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/outliers/boxplot?formato=json",
        "endpoint_html": "/api/v1/visualizaciones/outliers/boxplot",
        "parametros_principales": ["formato"],
    },
    {
        "id_visualizacion": "perfil_radar",
        "titulo": "Perfil Radar Multidimensional por Departamento",
        "categoria": "Tendencias y Estadística",
        "tipo_grafica": "radar",
        "descripcion": "Comparación radial normalizada entre un departamento y otra entidad o media nacional.",
        "soporta_3d": False,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/perfil/radar?depto_codigo=13&formato=json",
        "endpoint_html": "/api/v1/visualizaciones/perfil/radar?depto_codigo=13",
        "parametros_principales": ["depto_codigo", "comparar_con"],
    },
    {
        "id_visualizacion": "mapa_3d_relieve",
        "titulo": "Mapa 3D con Relieve Volumétrico (Deck.gl)",
        "categoria": "Cartografía 2D, Relieve 3D y Blender",
        "tipo_grafica": "map_3d_relief",
        "descripcion": "Relieve 3D interactivo de Guatemala con perspectivas, rotación 360 grados y modos de color.",
        "soporta_3d": True,
        "soporta_animacion": True,
        "endpoint_json": "/api/v1/visualizaciones/mapa/3d-relieve?indicador=tasa_retorno_migratorio_por_10k",
        "endpoint_html": "/api/v1/visualizaciones/mapa/3d-relieve?indicador=tasa_retorno_migratorio_por_10k",
        "parametros_principales": ["indicador", "estilo_color", "altura_max_m"],
    },
    {
        "id_visualizacion": "mapa_2d_plotly",
        "titulo": "Mapa Coroplético Interactivo 2D (Plotly + Panel)",
        "categoria": "Cartografía 2D, Relieve 3D y Blender",
        "tipo_grafica": "map_2d_plotly",
        "descripcion": "Coropleta departamental con panel lateral de KPIs nacionales y ranking ordenado.",
        "soporta_3d": False,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/mapa/2d-plotly?indicador=indice_vulnerabilidad_ivst&formato=json",
        "endpoint_html": "/api/v1/visualizaciones/mapa/2d-plotly?indicador=indice_vulnerabilidad_ivst&formato=html",
        "parametros_principales": ["indicador", "formato"],
    },
    {
        "id_visualizacion": "mapa_2d_folium",
        "titulo": "Mapa Geográfico Multicapa (Folium / Leaflet)",
        "categoria": "Cartografía 2D, Relieve 3D y Blender",
        "tipo_grafica": "map_2d_folium",
        "descripcion": "Mapa interactivo con capas satelital, relieve sombreado, calles y quiebres naturales.",
        "soporta_3d": False,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/mapa/2d-folium?indicador=tasa_necropsias_por_100k",
        "endpoint_html": "/api/v1/visualizaciones/mapa/2d-folium?indicador=tasa_necropsias_por_100k",
        "parametros_principales": ["indicador", "esquema_color", "capa_base"],
    },
    {
        "id_visualizacion": "modelo_3d_impresion_blender",
        "titulo": "Modelo 3D Exportable para Blender e Impresión (GLB / STL / ZIP / OBJ)",
        "categoria": "Cartografía 2D, Relieve 3D y Blender",
        "tipo_grafica": "model_3d",
        "descripcion": "Escena 3D física con 22 departamentos separados, materiales PBR de color y base de silueta.",
        "soporta_3d": True,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/mapa/modelo-3d?indicador=tasa_victimas_viales_por_100k&formato=glb",
        "endpoint_html": None,
        "parametros_principales": ["indicador", "formato", "estilo_color", "grosor_base_mm"],
    },
    {
        "id_visualizacion": "render_3d_blender",
        "titulo": "Renderizado 3D de Estudio con Blender Headless (PNG)",
        "categoria": "Cartografía 2D, Relieve 3D y Blender",
        "tipo_grafica": "blender_render",
        "descripcion": "Imagen renderizada fotorrealista mediante Blender sobre cualquier indicador socioeconómico.",
        "soporta_3d": True,
        "soporta_animacion": False,
        "endpoint_json": "/api/v1/visualizaciones/mapa/render-blender?indicador=indice_vulnerabilidad_ivst",
        "endpoint_html": "/api/v1/visualizaciones/mapa/render-blender?indicador=indice_vulnerabilidad_ivst",
        "parametros_principales": ["indicador", "estilo_color", "ancho_px", "alto_px"],
    },
]


def _render_chart_result(result: Union[Dict[str, Any], str], output_format: str) -> Any:
    # retornar respuesta html interactiva o especificacion json para el frontend
    if output_format.lower().strip() == "html" and isinstance(result, str):
        return HTMLResponse(content=result)
    return JSONResponse(content=result)


@router.get("/catalogo", response_model=VisualizationCatalogResponse, summary="Catálogo maestro de visualizaciones e indicadores")
def get_visualizations_catalog():
    indicators_list = [
        {
            "codigo": code,
            "titulo": meta["titulo"],
            "unidad": meta["unidad"],
            "dominio": meta["dominio"],
        }
        for code, meta in INDICATORS_CATALOG.items()
    ]
    return VisualizationCatalogResponse(
        total_visualizaciones=len(VISUALIZATION_CATALOG_ITEMS),
        total_indicadores=len(indicators_list),
        indicadores_disponibles=indicators_list,
        visualizaciones=VISUALIZATION_CATALOG_ITEMS,
    )


@router.get("/3d/trayectoria-demografica", summary="Gráfica 3D animada de trayectoria demográfica (2015-2030)")
def get_3d_demographic_trajectory(
    color_por: str = Query(default="region_nombre", description="Agrupacion de color: region_nombre, cluster_nombre o nivel_vulnerabilidad"),
    formato: str = Query(default="html", pattern="^(html|json)$", description="html listo para visualizar directamente o json para frontend"),
    regenerar: bool = Query(default=False, description="Forzar recalculado ignorando cache en disco"),
):
    try:
        cache_key = f"3d_trayectoria_demografica_{color_por}"
        res = get_or_build_chart(
            cache_key, formato, lambda output_format: build_3d_demographic_trajectory_chart(color_by=color_por, output_format=output_format), force_refresh=regenerar
        )
        return _render_chart_result(res, formato)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando grafica 3d demografica: {exc}")


@router.get("/3d/clusters-pca", summary="Gráfica 3D de componentes principales (PCA) y clústeres K-Means")
def get_3d_pca_clusters(
    formato: str = Query(default="html", pattern="^(html|json)$"),
    regenerar: bool = Query(default=False),
):
    try:
        res = get_or_build_chart(
            "3d_clusters_pca", formato, lambda output_format: build_3d_pca_clusters_chart(output_format=output_format), force_refresh=regenerar
        )
        return _render_chart_result(res, formato)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando grafica 3d pca: {exc}")


@router.get("/3d/riesgo-multidimensional", summary="Dispersión 3D personalizable de indicadores departamentales")
def get_3d_multidimensional_scatter(
    eje_x: str = Query(default="tasa_retorno_migratorio_por_10k", description="Indicador para eje X"),
    eje_y: str = Query(default="tasa_matricula_superior_por_10k", description="Indicador para eje Y"),
    eje_z: str = Query(default="tasa_necropsias_por_100k", description="Indicador para eje Z"),
    color_por: str = Query(default="nivel_vulnerabilidad", description="Variable categorica o numerica para color"),
    tamano_por: str = Query(default="poblacion_total", description="Variable numerica para tamano de esfera"),
    formato: str = Query(default="html", pattern="^(html|json)$"),
    regenerar: bool = Query(default=False),
):
    try:
        cache_key = f"3d_riesgo_{eje_x}_{eje_y}_{eje_z}_{color_por}_{tamano_por}"
        res = get_or_build_chart(
            cache_key,
            formato,
            lambda output_format: build_3d_multidimensional_scatter_chart(
                x_col=eje_x, y_col=eje_y, z_col=eje_z, color_col=color_por, size_col=tamano_por, output_format=output_format
            ),
            force_refresh=regenerar,
        )
        return _render_chart_result(res, formato)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando cubo 3d: {exc}")


@router.get("/3d/trayectoria-costo-vida", summary="Trayectoria 3D animada de la Canasta Básica Alimentaria")
def get_3d_cost_of_living_trajectory(
    formato: str = Query(default="html", pattern="^(html|json)$"),
    regenerar: bool = Query(default=False),
):
    try:
        res = get_or_build_chart(
            "3d_trayectoria_costo_vida", formato, lambda output_format: build_3d_cost_of_living_trajectory_chart(output_format=output_format), force_refresh=regenerar
        )
        return _render_chart_result(res, formato)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando trayectoria 3d cba: {exc}")


@router.get("/barras/ranking-departamental", summary="Gráfica de barras de ranking departamental")
def get_department_ranking_bars(
    indicador: str = Query(default="tasa_retorno_migratorio_por_10k"),
    top_n: int = Query(default=22, ge=3, le=22),
    orden: str = Query(default="desc", pattern="^(asc|desc)$"),
    orientacion: str = Query(default="h", pattern="^(h|v)$"),
    color_por: str = Query(default="nivel_vulnerabilidad"),
    formato: str = Query(default="html", pattern="^(html|json)$"),
    regenerar: bool = Query(default=False),
):
    try:
        cache_key = f"barras_depto_v2_{indicador}_{top_n}_{orden}_{orientacion}_{color_por}"
        res = get_or_build_chart(
            cache_key,
            formato,
            lambda output_format: build_department_ranking_bar_chart(
                indicator=indicador, top_n=top_n, order=orden, orientation=orientacion, color_by=color_por, output_format=output_format
            ),
            force_refresh=regenerar,
        )
        return _render_chart_result(res, formato)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando barras departamentales: {exc}")


@router.get("/barras/ranking-municipal", summary="Gráfica de barras a escala municipal (340 municipios)")
def get_municipal_ranking_bars(
    indicador: str = Query(default="tasa_necropsias_por_100k"),
    depto_codigo: Optional[int] = Query(default=None, ge=1, le=22),
    top_n: int = Query(default=20, ge=3, le=50),
    formato: str = Query(default="html", pattern="^(html|json)$"),
    regenerar: bool = Query(default=False),
):
    try:
        depto_tag = str(depto_codigo) if depto_codigo is not None else "all"
        cache_key = f"barras_muni_v2_{indicador}_{depto_tag}_{top_n}"
        res = get_or_build_chart(
            cache_key,
            formato,
            lambda output_format: build_municipal_ranking_bar_chart(
                indicator=indicador, depto_codigo=depto_codigo, top_n=top_n, output_format=output_format
            ),
            force_refresh=regenerar,
        )
        return _render_chart_result(res, formato)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando barras municipales: {exc}")


@router.get("/barras/estructura-demografica", summary="Barras apiladas 100% de estructura poblacional por edades")
def get_demographic_structure_bars(
    formato: str = Query(default="html", pattern="^(html|json)$"),
    regenerar: bool = Query(default=False),
):
    try:
        res = get_or_build_chart(
            "barras_estructura_demografica", formato, lambda output_format: build_demographic_structure_stacked_bar_chart(output_format=output_format), force_refresh=regenerar
        )
        return _render_chart_result(res, formato)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando estructura demografica: {exc}")


@router.get("/barras/composicion-retornados", summary="Barras agrupadas de composición etaria y género de retornados")
def get_returnees_composition_bars(
    top_n: int = Query(default=12, ge=3, le=22),
    formato: str = Query(default="html", pattern="^(html|json)$"),
    regenerar: bool = Query(default=False),
):
    try:
        res = get_or_build_chart(
            f"barras_composicion_retornados_{top_n}", formato, lambda output_format: build_returnees_composition_bar_chart(top_n=top_n, output_format=output_format), force_refresh=regenerar
        )
        return _render_chart_result(res, formato)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando barras retornados: {exc}")


@router.get("/pastel/distribucion", summary="Gráficas de pastel, dona y sunburst territorial")
def get_pie_distribution(
    tipo: str = Query(
        default="clusters",
        description="Tipo: clusters, retornados_edad, retornados_genero, educacion_genero, victimas_viales, estructura_etaria o jerarquia_territorial",
    ),
    depto_codigo: Optional[int] = Query(default=None, ge=1, le=22, description="Filtrar por departamento cuando aplica"),
    metrica: str = Query(default="poblacion_total", description="Metrica cuantitativa para clusters o sunburst"),
    formato: str = Query(default="html", pattern="^(html|json)$"),
    regenerar: bool = Query(default=False),
):
    try:
        depto_tag = str(depto_codigo) if depto_codigo is not None else "all"
        cache_key = f"pastel_{tipo}_{depto_tag}_{metrica}"
        res = get_or_build_chart(
            cache_key,
            formato,
            lambda output_format: build_pie_distribution_chart(
                chart_type=tipo, depto_codigo=depto_codigo, metric=metrica, output_format=output_format
            ),
            force_refresh=regenerar,
        )
        return _render_chart_result(res, formato)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando grafica pastel: {exc}")


@router.get("/tendencias/costo-vida", summary="Serie temporal y proyección a 12 meses de CBA urbana y rural")
def get_cost_of_living_trend_chart(
    formato: str = Query(default="html", pattern="^(html|json)$"),
    regenerar: bool = Query(default=False),
):
    try:
        res = get_or_build_chart(
            "tendencia_costo_vida", formato, lambda output_format: build_cost_of_living_forecast_chart(output_format=output_format), force_refresh=regenerar
        )
        return _render_chart_result(res, formato)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando tendencia cba: {exc}")


@router.get("/tendencias/ipc", summary="Tendencias de inflación regional, divisiones de gasto y poder adquisitivo")
def get_ipc_trends(
    vista: str = Query(default="regiones", pattern="^(regiones|divisiones|poder_adquisitivo)$"),
    formato: str = Query(default="html", pattern="^(html|json)$"),
    regenerar: bool = Query(default=False),
):
    try:
        res = get_or_build_chart(
            f"tendencia_ipc_{vista}", formato, lambda output_format: build_ipc_trends_chart(view=vista, output_format=output_format), force_refresh=regenerar
        )
        return _render_chart_result(res, formato)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando tendencia ipc: {exc}")


@router.get("/tendencias/crecimiento-demografico", summary="Curvas demográficas departamentales 2015-2030")
def get_demographic_growth_lines(
    top_n: int = Query(default=8, ge=2, le=22),
    formato: str = Query(default="html", pattern="^(html|json)$"),
    regenerar: bool = Query(default=False),
):
    try:
        res = get_or_build_chart(
            f"tendencia_demografica_{top_n}", formato, lambda output_format: build_demographic_growth_lines_chart(top_n=top_n, output_format=output_format), force_refresh=regenerar
        )
        return _render_chart_result(res, formato)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando lineas demograficas: {exc}")


@router.get("/correlaciones/heatmap", summary="Mapa de calor interactivo de correlaciones Pearson/Spearman")
def get_correlation_heatmap(
    metodo: str = Query(default="pearson", pattern="^(pearson|spearman)$"),
    formato: str = Query(default="html", pattern="^(html|json)$"),
    regenerar: bool = Query(default=False),
):
    try:
        res = get_or_build_chart(
            f"heatmap_{metodo}", formato, lambda output_format: build_correlation_heatmap_chart(method=metodo, output_format=output_format), force_refresh=regenerar
        )
        return _render_chart_result(res, formato)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando heatmap correlaciones: {exc}")


@router.get("/outliers/boxplot", summary="Boxplots estandarizados Z-score con detección de outliers")
def get_outliers_boxplot(
    formato: str = Query(default="html", pattern="^(html|json)$"),
    regenerar: bool = Query(default=False),
):
    try:
        res = get_or_build_chart(
            "boxplot_outliers", formato, lambda output_format: build_outliers_boxplot_chart(output_format=output_format), force_refresh=regenerar
        )
        return _render_chart_result(res, formato)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando boxplot outliers: {exc}")


@router.get("/perfil/radar", summary="Gráfica radar comparativa multidimensional por departamento")
def get_department_radar(
    depto_codigo: int = Query(default=13, ge=1, le=22, description="Codigo del departamento principal (ej. 13 = Huehuetenango)"),
    comparar_con: Optional[int] = Query(default=1, ge=1, le=22, description="Departamento a comparar (omitir para media nacional)"),
    formato: str = Query(default="html", pattern="^(html|json)$"),
    regenerar: bool = Query(default=False),
):
    try:
        comp_tag = str(comparar_con) if comparar_con is not None else "nac"
        res = get_or_build_chart(
            f"radar_{depto_codigo}_{comp_tag}", formato, lambda output_format: build_department_radar_chart(depto_codigo=depto_codigo, compare_code=comparar_con, output_format=output_format), force_refresh=regenerar
        )
        return _render_chart_result(res, formato)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando perfil radar: {exc}")


# rutas cartograficas 2d, relieve 3d y blender conectadas directamente a los indicadores calculados
@router.get("/mapa/2d-folium", summary="Mapa coroplético 2D multicapa (Folium) sobre indicadores", response_class=HTMLResponse)
def get_indicators_folium_map(
    indicador: str = Query(default="tasa_retorno_migratorio_por_10k"),
    esquema_color: str = Query(default="YlOrRd"),
    capa_base: str = Query(default="Esri.WorldGrayCanvas"),
    descargar: bool = Query(default=False),
    regenerar: bool = Query(default=False),
):
    try:
        out_name = f"mapa_folium_{indicador}.html"
        out_path = PROCESSED_DATA_DIR / "mapas" / out_name
        disposition = "attachment" if descargar else "inline"

        if (
            not regenerar
            and esquema_color == "YlOrRd"
            and capa_base == "Esri.WorldGrayCanvas"
            and out_path.exists()
            and out_path.stat().st_size > 0
        ):
            return HTMLResponse(
                content=out_path.read_text(encoding="utf-8"),
                headers={"Content-Disposition": f'{disposition}; filename="{out_name}"'},
            )

        merged_gdf, meta = load_enriched_geo_dataframe(indicador)
        saved_html = export_folium_map(
            merged_gdf=merged_gdf,
            output_html_path=out_path,
            value_col=indicador,
            colormap=esquema_color,
            tooltip_cols=["nombre", indicador],
            tiles=capa_base,
            topic_title=meta["titulo"],
        )
        return HTMLResponse(
            content=saved_html.read_text(encoding="utf-8"),
            headers={"Content-Disposition": f'{disposition}; filename="{out_name}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando mapa folium de indicador: {exc}")


@router.get("/mapa/2d-plotly", summary="Mapa coroplético 2D (Plotly) sobre indicadores calculados")
def get_indicators_plotly_map(
    indicador: str = Query(default="indice_vulnerabilidad_ivst"),
    formato: str = Query(default="html", pattern="^(html|json)$"),
    descargar: bool = Query(default=False),
    regenerar: bool = Query(default=False),
):
    try:
        out_name = f"mapa_plotly_{indicador}.html"
        out_path = PROCESSED_DATA_DIR / "mapas" / out_name
        disposition = "attachment" if descargar else "inline"

        if formato == "html" and not regenerar and out_path.exists() and out_path.stat().st_size > 0:
            return HTMLResponse(
                content=out_path.read_text(encoding="utf-8"),
                headers={"Content-Disposition": f'{disposition}; filename="{out_name}"'},
            )

        merged_gdf, meta = load_enriched_geo_dataframe(indicador)
        fig = create_plotly_choropleth(
            merged_gdf=merged_gdf,
            code_col="cod",
            value_col=indicador,
            hover_name="nombre",
            topic_title=meta["titulo"],
        )

        if formato == "html":
            html_markup = fig.to_html(include_plotlyjs="cdn")
            sidebar = build_guatemala_sidebar_html(
                merged_gdf, value_col=indicador, name_col="nombre", topic_title=meta["titulo"]
            )
            if sidebar and "</body>" in html_markup:
                html_markup = html_markup.replace("</body>", f"{sidebar}</body>")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(html_markup, encoding="utf-8")
            return HTMLResponse(
                content=html_markup,
                headers={"Content-Disposition": f'{disposition}; filename="{out_name}"'},
            )

        plotly_spec = json.loads(fig.to_json())
        return JSONResponse(content={
            "indicador": indicador,
            "titulo": meta["titulo"],
            "unidad": meta["unidad"],
            "plotly_spec": plotly_spec,
        })
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando mapa plotly de indicador: {exc}")


@router.get("/mapa/3d-relieve", summary="Mapa 3D con relieve volumétrico (Deck.gl) sobre indicadores", response_class=HTMLResponse)
def get_indicators_3d_relief_map(
    indicador: str = Query(default="tasa_retorno_migratorio_por_10k"),
    estilo_color: str = Query(default="multicolor", pattern="^(multicolor|negro|calor)$"),
    altura_max_m: float = Query(default=65000.0, ge=5000.0, le=200000.0),
    descargar: bool = Query(default=False),
    regenerar: bool = Query(default=False),
):
    try:
        out_path = PROCESSED_DATA_DIR / "mapas" / f"mapa_3d_{indicador}_{estilo_color}.html"
        disposition = "attachment" if descargar else "inline"
        if not regenerar and abs(altura_max_m - 65000.0) < 1e-6 and out_path.exists() and out_path.stat().st_size > 0:
            return HTMLResponse(
                content=out_path.read_text(encoding="utf-8"),
                headers={"Content-Disposition": f'{disposition}; filename="mapa_3d_{indicador}.html"'},
            )

        merged_gdf, meta = load_enriched_geo_dataframe(indicador)
        html_out = build_deckgl_3d_relief_html(
            merged_gdf,
            value_col=indicador,
            name_col="nombre",
            code_col="cod",
            topic_title=meta["titulo"],
            color_mode=estilo_color,
            max_elevation_m=altura_max_m,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_out, encoding="utf-8")
        return HTMLResponse(
            content=html_out,
            headers={"Content-Disposition": f'{disposition}; filename="mapa_3d_{indicador}.html"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando relieve 3d de indicador: {exc}")


@router.get("/mapa/modelo-3d", summary="Exportar modelo 3D (GLB/STL/ZIP/OBJ) de Guatemala según indicador")
def get_indicators_3d_model(
    indicador: str = Query(default="tasa_retorno_migratorio_por_10k"),
    formato: str = Query(default="glb", pattern="^(glb|stl|zip|obj)$"),
    estilo_color: str = Query(default="multicolor", pattern="^(multicolor|negro|calor)$"),
    ancho_mm: float = Query(default=150.0, ge=40.0, le=500.0),
    altura_max_mm: float = Query(default=60.0, ge=5.0, le=200.0),
    grosor_base_mm: float = Query(default=0.6, ge=0.0, le=20.0),
    forma_base: str = Query(default="silueta", pattern="^(silueta|caja|ninguna)$"),
    regenerar: bool = Query(default=False),
):
    try:
        import trimesh
        import zipfile

        out_dir = PROCESSED_DATA_DIR / "modelos_3d"
        out_dir.mkdir(parents=True, exist_ok=True)
        fmt = formato.lower().strip()
        is_default_geom = (
            abs(ancho_mm - 150.0) < 1e-6
            and abs(altura_max_mm - 60.0) < 1e-6
            and abs(grosor_base_mm - 0.6) < 1e-6
            and forma_base == "silueta"
        )
        glb_cache = out_dir / f"modelo_3d_{indicador}_{estilo_color}.glb"
        if fmt == "glb" and is_default_geom and not regenerar and glb_cache.exists() and glb_cache.stat().st_size > 0:
            return FileResponse(str(glb_cache), media_type="model/gltf-binary", filename=glb_cache.name)

        merged_gdf, _ = load_enriched_geo_dataframe(indicador)
        scene = build_guatemala_relief_scene(
            merged_gdf,
            value_col=indicador,
            code_col="cod",
            name_col="nombre",
            target_width_mm=ancho_mm,
            base_mm=grosor_base_mm,
            forma_base=forma_base,
            max_relief_mm=altura_max_mm,
            add_camera=(formato == "glb"),
            color_mode=estilo_color,
        )

        if fmt == "zip":
            out_file = out_dir / f"modelos_stl_{indicador}.zip"
            with zipfile.ZipFile(out_file, "w", zipfile.ZIP_DEFLATED) as zf:
                for geom_name, geom in scene.geometry.items():
                    zf.writestr(f"{geom_name}.stl", geom.export(file_type="stl"))
            return FileResponse(str(out_file), media_type="application/zip", filename=out_file.name)

        if fmt == "stl":
            out_file = out_dir / f"modelo_3d_{indicador}.stl"
            solid = trimesh.util.concatenate(list(scene.geometry.values()))
            solid.export(str(out_file))
            return FileResponse(str(out_file), media_type="model/stl", filename=out_file.name)

        if fmt == "obj":
            out_file = out_dir / f"modelo_3d_{indicador}.obj"
            out_file.write_text(scene.export(file_type="obj"), encoding="utf-8")
            return FileResponse(str(out_file), media_type="text/plain", filename=out_file.name)

        out_file = glb_cache if is_default_geom else (out_dir / f"modelo_3d_{indicador}.glb")
        scene.export(str(out_file))
        return FileResponse(str(out_file), media_type="model/gltf-binary", filename=out_file.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error generando modelo 3d del indicador: {exc}")


@router.get("/mapa/render-blender", summary="Renderizar en Blender PNG de alta resolución sobre indicador")
def get_indicators_blender_render(
    indicador: str = Query(default="indice_vulnerabilidad_ivst"),
    estilo_color: str = Query(default="multicolor", pattern="^(multicolor|negro|azul)$"),
    grosor_base_mm: float = Query(default=0.6, ge=0.0, le=20.0),
    ancho_px: int = Query(default=1280, ge=320, le=3840),
    alto_px: int = Query(default=720, ge=240, le=2160),
    descargar: bool = Query(default=False),
    regenerar: bool = Query(default=False),
):
    try:
        out_dir = PROCESSED_DATA_DIR / "renders_blender"
        out_dir.mkdir(parents=True, exist_ok=True)
        glb_path = out_dir / f"escena_{indicador}_{estilo_color}.glb"
        png_path = out_dir / f"render_blender_{indicador}_{estilo_color}_{ancho_px}x{alto_px}.png"

        # reutilizar render pregenerado valido si existe y no se solicita regenerar
        is_valid_cached_png = (
            png_path.exists()
            and png_path.stat().st_size > 100
            and png_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        )
        if not regenerar and abs(grosor_base_mm - 0.6) < 1e-6 and is_valid_cached_png:
            disposition = "attachment" if descargar else "inline"
            return FileResponse(
                str(png_path),
                media_type="image/png",
                headers={"Content-Disposition": f'{disposition}; filename="{png_path.name}"'},
            )

        merged_gdf, _ = load_enriched_geo_dataframe(indicador)
        scene = build_guatemala_relief_scene(
            merged_gdf,
            value_col=indicador,
            code_col="cod",
            name_col="nombre",
            target_width_mm=150.0,
            base_mm=grosor_base_mm,
            forma_base="silueta",
            max_relief_mm=60.0,
            add_camera=True,
            color_mode=estilo_color,
        )
        scene.export(str(glb_path))

        render_guatemala_with_blender(
            glb_path=glb_path,
            output_png_path=png_path,
            width=ancho_px,
            height=alto_px,
            color_mode=estilo_color,
        )
        disposition = "attachment" if descargar else "inline"
        return FileResponse(
            str(png_path),
            media_type="image/png",
            headers={"Content-Disposition": f'{disposition}; filename="{png_path.name}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"error renderizando en blender: {exc}")


# portal interactivo de referencia consumiendo el stack completo desde el navegador
@router.get("/stack-completo", summary="Visor interactivo unificado del stack visual completo", response_class=HTMLResponse)
def get_full_visualization_stack_portal():
    options_html = "".join(
        f'<option value="{code}">{meta["dominio"]}: {meta["titulo"]}</option>'
        for code, meta in INDICATORS_CATALOG.items()
    )
    html_page = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Balam Data Systems — Stack Interactivo 2D, 3D y Blender</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    :root {{
      --bg: #070b14; --card: #0f172a; --border: #1e293b;
      --accent: #38bdf8; --text: #f8fafc; --muted: #94a3b8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: Inter, system-ui, -apple-system, sans-serif;
      background: var(--bg); color: var(--text);
    }}
    header {{
      background: linear-gradient(135deg, #0f172a, #172554);
      border-bottom: 1px solid var(--border); padding: 16px 24px;
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 14px;
    }}
    .brand h1 {{ margin: 0; font-size: 18px; letter-spacing: -0.3px; }}
    .brand p {{ margin: 2px 0 0; font-size: 12px; color: var(--muted); }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    select, button {{
      background: #1e293b; color: var(--text); border: 1px solid #334155;
      border-radius: 8px; padding: 8px 12px; font-size: 13px; cursor: pointer;
    }}
    button.primary {{ background: #0284c7; border-color: #38bdf8; font-weight: 600; }}
    nav.tabs {{
      display: flex; gap: 8px; padding: 12px 24px; background: #0b1120;
      border-bottom: 1px solid var(--border); overflow-x: auto;
    }}
    .tab-btn {{
      background: transparent; border: 1px solid var(--border); color: var(--muted);
      padding: 8px 14px; border-radius: 8px; font-weight: 600; white-space: nowrap;
    }}
    .tab-btn.active {{ background: #0284c7; border-color: #38bdf8; color: #fff; }}
    main {{ padding: 20px 24px; max-width: 1600px; margin: 0 auto; }}
    .grid-2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(560px, 1fr)); gap: 18px; }}
    .card {{
      background: var(--card); border: 1px solid var(--border); border-radius: 14px;
      padding: 14px; box-shadow: 0 10px 25px rgba(0,0,0,0.35);
    }}
    .chart-box {{ width: 100%; min-height: 540px; }}
    .map-frame {{ width: 100%; height: 640px; border: none; border-radius: 10px; background: #050811; }}
    .hidden {{ display: none; }}
    .actions-row {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; align-items: center; }}
    .btn-link {{
      display: inline-block; text-decoration: none; background: #1e293b; color: #38bdf8;
      border: 1px solid #334155; padding: 7px 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
    }}
    .btn-link:hover {{ background: #0284c7; color: #fff; }}
    .blender-preview {{ width: 100%; max-height: 620px; object-fit: contain; border-radius: 10px; border: 1px solid var(--border); }}
  </style>
</head>
<body>
<header>
  <div class="brand">
    <h1>🇬🇹 Balam Data Systems — Stack Analítico Interactivo (INE 2026)</h1>
    <p>Consumo en vivo de API REST: Gráficas 3D animadas, Barras, Pastel/Sunburst, Tendencias, Relieve 3D Deck.gl y Blender</p>
  </div>
  <div class="controls">
    <label for="indicator-select" style="font-size:12px; color:var(--muted);">Indicador activo:</label>
    <select id="indicator-select" onchange="refreshActiveTab()">
      {options_html}
    </select>
    <a class="btn-link" href="/docs" target="_blank">📚 API Scalar Docs</a>
  </div>
</header>

<nav class="tabs">
  <button class="tab-btn active" onclick="switchTab('tab-3d', this)">🧊 Gráficas 3D y Movimiento</button>
  <button class="tab-btn" onclick="switchTab('tab-bars', this)">📊 Barras y Rankings</button>
  <button class="tab-btn" onclick="switchTab('tab-pies', this)">🥧 Pastel, Donas y Sunburst</button>
  <button class="tab-btn" onclick="switchTab('tab-trends', this)">📈 Tendencias, Heatmap y Radar</button>
  <button class="tab-btn" onclick="switchTab('tab-maps', this)">🗺️ Mapas 2D & Relieve 3D Deck.gl</button>
  <button class="tab-btn" onclick="switchTab('tab-blender', this)">🎬 Blender 3D & Modelos STL/GLB</button>
</nav>

<main>
  <section id="tab-3d" class="tab-panel">
    <div class="grid-2">
      <div class="card"><div id="chart-3d-traj" class="chart-box"></div></div>
      <div class="card"><div id="chart-3d-pca" class="chart-box"></div></div>
      <div class="card"><div id="chart-3d-risk" class="chart-box"></div></div>
      <div class="card"><div id="chart-3d-cba" class="chart-box"></div></div>
    </div>
  </section>

  <section id="tab-bars" class="tab-panel hidden">
    <div class="grid-2">
      <div class="card"><div id="chart-bar-dept" class="chart-box"></div></div>
      <div class="card"><div id="chart-bar-muni" class="chart-box"></div></div>
      <div class="card"><div id="chart-bar-age" class="chart-box"></div></div>
      <div class="card"><div id="chart-bar-ret" class="chart-box"></div></div>
    </div>
  </section>

  <section id="tab-pies" class="tab-panel hidden">
    <div class="grid-2">
      <div class="card"><div id="chart-pie-clusters" class="chart-box"></div></div>
      <div class="card"><div id="chart-pie-sunburst" class="chart-box"></div></div>
      <div class="card"><div id="chart-pie-ret-edad" class="chart-box"></div></div>
      <div class="card"><div id="chart-pie-edu-gen" class="chart-box"></div></div>
    </div>
  </section>

  <section id="tab-trends" class="tab-panel hidden">
    <div class="grid-2">
      <div class="card"><div id="chart-trend-cba" class="chart-box"></div></div>
      <div class="card"><div id="chart-trend-ipc" class="chart-box"></div></div>
      <div class="card"><div id="chart-heatmap" class="chart-box"></div></div>
      <div class="card"><div id="chart-radar" class="chart-box"></div></div>
    </div>
  </section>

  <section id="tab-maps" class="tab-panel hidden">
    <div class="grid-2">
      <div class="card">
        <div class="actions-row">
          <b>Relieve 3D Interactivo (Deck.gl)</b>
          <a id="link-3d-full" class="btn-link" target="_blank">Abrir pantalla completa ↗</a>
        </div>
        <iframe id="frame-3d-relief" class="map-frame"></iframe>
      </div>
      <div class="card">
        <div class="actions-row">
          <b>Mapa Coroplético 2D (Plotly + Panel INE)</b>
          <a id="link-2d-folium" class="btn-link" target="_blank">Ver en Folium Multicapa ↗</a>
        </div>
        <iframe id="frame-2d-plotly" class="map-frame"></iframe>
      </div>
    </div>
  </section>

  <section id="tab-blender" class="tab-panel hidden">
    <div class="card">
      <div class="actions-row">
        <b>Exportación 3D e Iluminación de Estudio en Blender</b>
        <select id="blender-style" onchange="loadBlenderTab()">
          <option value="multicolor">Estilo 22 Colores Departamentales</option>
          <option value="negro">Estilo Relieve Negro Escultórico</option>
          <option value="azul">Estilo Azul Petróleo</option>
        </select>
        <button class="primary" onclick="loadBlenderTab()">🎬 Generar Render Blender PNG</button>
        <a id="dl-glb" class="btn-link">⬇ Descargar Escena .GLB (Blender)</a>
        <a id="dl-stl" class="btn-link">⬇ Descargar Sólido .STL (Impresión 3D)</a>
        <a id="dl-zip" class="btn-link">⬇ Descargar Pack 22 STLs .ZIP</a>
      </div>
      <p id="blender-status" style="font-size:12px; color:var(--muted); margin:6px 0 12px;">
        Haga clic en "Generar Render Blender PNG" o seleccione un estilo para renderizar el indicador activo con Blender 3D headless.
      </p>
      <img id="blender-img" class="blender-preview hidden" alt="Render 3D Blender de Guatemala"/>
    </div>
  </section>
</main>

<script>
const BASE = '/api/v1/visualizaciones';
let activeTabId = 'tab-3d';

function selectedIndicator() {{
  return document.getElementById('indicator-select').value;
}}

async function renderPlotlyFromApi(divId, url) {{
  const el = document.getElementById(divId);
  el.innerHTML = '<div style="padding:40px; text-align:center; color:#94a3b8;">Cargando visualización...</div>';
  try {{
    const res = await fetch(url);
    const json = await res.json();
    el.innerHTML = '';
    const spec = json.plotly_spec;
    Plotly.newPlot(el, spec.data, spec.layout, {{ responsive: true, displaylogo: false }}).then(() => {{
      if (spec.frames && spec.frames.length > 0) {{
        Plotly.addFrames(el, spec.frames);
      }}
    }});
  }} catch (err) {{
    el.innerHTML = '<div style="padding:20px; color:#f43f5e;">Error cargando gráfica: ' + err + '</div>';
  }}
}}

function switchTab(tabId, btn) {{
  activeTabId = tabId;
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
  document.getElementById(tabId).classList.remove('hidden');
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  refreshActiveTab();
}}

function refreshActiveTab() {{
  const ind = selectedIndicator();
  if (activeTabId === 'tab-3d') {{
    renderPlotlyFromApi('chart-3d-traj', `${{BASE}}/3d/trayectoria-demografica?formato=json`);
    renderPlotlyFromApi('chart-3d-pca', `${{BASE}}/3d/clusters-pca?formato=json`);
    renderPlotlyFromApi('chart-3d-risk', `${{BASE}}/3d/riesgo-multidimensional?eje_x=${{encodeURIComponent(ind)}}&formato=json`);
    renderPlotlyFromApi('chart-3d-cba', `${{BASE}}/3d/trayectoria-costo-vida?formato=json`);
  }} else if (activeTabId === 'tab-bars') {{
    const muniInd = ['tasa_necropsias_por_100k', 'tasa_victimas_viales_por_100k', 'tasa_matricula_superior_por_10k', 'tasa_natalidad_por_1000', 'tasa_mortalidad_por_1000'].includes(ind)
      ? ind : 'tasa_necropsias_por_100k';
    renderPlotlyFromApi('chart-bar-dept', `${{BASE}}/barras/ranking-departamental?indicador=${{encodeURIComponent(ind)}}&formato=json`);
    renderPlotlyFromApi('chart-bar-muni', `${{BASE}}/barras/ranking-municipal?indicador=${{encodeURIComponent(muniInd)}}&formato=json`);
    renderPlotlyFromApi('chart-bar-age', `${{BASE}}/barras/estructura-demografica?formato=json`);
    renderPlotlyFromApi('chart-bar-ret', `${{BASE}}/barras/composicion-retornados?formato=json`);
  }} else if (activeTabId === 'tab-pies') {{
    renderPlotlyFromApi('chart-pie-clusters', `${{BASE}}/pastel/distribucion?tipo=clusters&formato=json`);
    renderPlotlyFromApi('chart-pie-sunburst', `${{BASE}}/pastel/distribucion?tipo=jerarquia_territorial&metrica=poblacion_total&formato=json`);
    renderPlotlyFromApi('chart-pie-ret-edad', `${{BASE}}/pastel/distribucion?tipo=retornados_edad&formato=json`);
    renderPlotlyFromApi('chart-pie-edu-gen', `${{BASE}}/pastel/distribucion?tipo=educacion_genero&formato=json`);
  }} else if (activeTabId === 'tab-trends') {{
    renderPlotlyFromApi('chart-trend-cba', `${{BASE}}/tendencias/costo-vida?formato=json`);
    renderPlotlyFromApi('chart-trend-ipc', `${{BASE}}/tendencias/ipc?vista=regiones&formato=json`);
    renderPlotlyFromApi('chart-heatmap', `${{BASE}}/correlaciones/heatmap?metodo=pearson&formato=json`);
    renderPlotlyFromApi('chart-radar', `${{BASE}}/perfil/radar?depto_codigo=13&comparar_con=1&formato=json`);
  }} else if (activeTabId === 'tab-maps') {{
    const url3d = `${{BASE}}/mapa/3d-relieve?indicador=${{encodeURIComponent(ind)}}`;
    const url2d = `${{BASE}}/mapa/2d-plotly?indicador=${{encodeURIComponent(ind)}}&formato=html`;
    const urlFol = `${{BASE}}/mapa/2d-folium?indicador=${{encodeURIComponent(ind)}}`;
    document.getElementById('frame-3d-relief').src = url3d;
    document.getElementById('frame-2d-plotly').src = url2d;
    document.getElementById('link-3d-full').href = url3d;
    document.getElementById('link-2d-folium').href = urlFol;
  }} else if (activeTabId === 'tab-blender') {{
    loadBlenderTab();
  }}
}}

function updateBlenderLinks() {{
  const ind = selectedIndicator();
  const style = document.getElementById('blender-style').value;
  const colMode = style === 'azul' ? 'calor' : style;
  document.getElementById('dl-glb').href = `${{BASE}}/mapa/modelo-3d?indicador=${{encodeURIComponent(ind)}}&formato=glb&estilo_color=${{colMode}}`;
  document.getElementById('dl-stl').href = `${{BASE}}/mapa/modelo-3d?indicador=${{encodeURIComponent(ind)}}&formato=stl`;
  document.getElementById('dl-zip').href = `${{BASE}}/mapa/modelo-3d?indicador=${{encodeURIComponent(ind)}}&formato=zip`;
}}

function loadBlenderTab() {{
  updateBlenderLinks();
  const ind = selectedIndicator();
  const style = document.getElementById('blender-style').value;
  const img = document.getElementById('blender-img');
  const status = document.getElementById('blender-status');
  status.innerText = 'Renderizando escena 3D en Blender para ' + ind + ' (' + style + ')... esto puede tardar unos segundos.';
  img.classList.add('hidden');
  img.onload = () => {{
    img.classList.remove('hidden');
    status.innerText = 'Render Blender completado para ' + ind + ' (' + style + ').';
  }};
  img.onerror = () => {{
    status.innerText = 'Error al generar render Blender en el servidor.';
  }};
  img.src = `${{BASE}}/mapa/render-blender?indicador=${{encodeURIComponent(ind)}}&estilo_color=${{style}}&t=${{Date.now()}}`;
}}

refreshActiveTab();
</script>
</body>
</html>"""
    return HTMLResponse(content=html_page)
