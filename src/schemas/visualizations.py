from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VisualizationMetadataItem(BaseModel):
    id_visualizacion: str
    titulo: str
    categoria: str
    tipo_grafica: str
    descripcion: str
    soporta_3d: bool
    soporta_animacion: bool
    endpoint_json: str
    endpoint_html: Optional[str] = None
    parametros_principales: List[str] = Field(default_factory=list)


class IndicatorCatalogOption(BaseModel):
    codigo: str
    titulo: str
    unidad: str
    dominio: str


class VisualizationCatalogResponse(BaseModel):
    total_visualizaciones: int
    total_indicadores: int
    indicadores_disponibles: List[IndicatorCatalogOption]
    visualizaciones: List[VisualizationMetadataItem]


class PlotlyChartJsonResponse(BaseModel):
    chart_id: str
    titulo: str
    subtitulo: str
    tipo_grafica: str
    datos_resumen: Dict[str, Any]
    plotly_spec: Dict[str, Any]
