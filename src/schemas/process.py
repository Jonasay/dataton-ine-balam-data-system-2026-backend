from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExcelToParquetRequest(BaseModel):
    """Modelo para la conversion de archivos excel a formato parquet."""
    ruta_excel: str = Field(..., description="Ruta relativa o nombre del archivo excel en el directorio raw")
    hoja_id: int = Field(default=1, ge=0, description="Indice o identificador de la hoja a convertir")
    ruta_salida_parquet: Optional[str] = Field(default=None, description="Ruta opcional de destino para el archivo parquet")
    compresion: str = Field(default="zstd", description="Algoritmo de compresion para parquet (ej. zstd o snappy)")


class ParquetAggregateRequest(BaseModel):
    """Modelo para agregar y resumir registros de parquet sin sentencias sql manuales."""
    ruta_parquet: str = Field(..., description="Ruta o nombre del archivo parquet en el directorio processed")
    agrupar_por: str = Field(..., description="Nombre de la columna para agrupar (ej. depto_ocu, tipo_veh)")
    columna_filtro: Optional[str] = Field(default=None, description="Columna opcional para filtrar antes de agrupar")
    valor_filtro: Optional[Any] = Field(default=None, description="Valor para el filtro opcional")
    limite: int = Field(default=10, ge=1, le=10000, description="Cantidad maxima de resultados ordenados por conteo")


class MapIndicatorItem(BaseModel):
    """Modelo de metadatos para un indicador departamental cartografiable."""
    id: str = Field(..., description="Identificador unico del indicador y periodo")
    tema: str = Field(..., description="Area tematica del indicador")
    indicador: str = Field(..., description="Nombre descriptivo del indicador")
    periodo: int = Field(..., description="Anio de referencia del indicador")
    ruta_parquet: str = Field(..., description="Ruta relativa del parquet en data/processed")
    columna_codigo_parquet: str = Field(default="depto_codigo", description="Columna de codigo departamental en parquet")
    columna_valor: str = Field(default="valor", description="Columna numerica a graficar en el mapa")
    unidad: str = Field(default="", description="Unidad de medida del indicador")
    titulo_mapa: str = Field(..., description="Titulo descriptivo para el mapa")


class MapIndicatorsResponse(BaseModel):
    """Modelo de respuesta del catalogo de indicadores disponibles para mapas."""
    total: int = Field(..., description="Cantidad total de indicadores disponibles")
    indicadores: List[MapIndicatorItem] = Field(default_factory=list, description="Listado de indicadores disponibles")


class DatasetChartPoint(BaseModel):
    """Punto individual dentro de una serie grafica procesada."""
    etiqueta: str
    valor: float
    porcentaje: float = 0.0


class DatasetChartItem(BaseModel):
    """Definicion estructurada de una grafica generada automaticamente."""
    id: str
    titulo: str
    subtitulo: str
    tipo: str
    eje_x: str
    eje_y: str
    datos: List[DatasetChartPoint] = Field(default_factory=list)


class DatasetColumnStat(BaseModel):
    """Resumen estadistico de una columna numerica del conjunto procesado."""
    columna: str
    conteo: int
    minimo: Optional[float] = None
    maximo: Optional[float] = None
    promedio: Optional[float] = None
    mediana: Optional[float] = None
    suma: Optional[float] = None


class CuratedVisualizationLink(BaseModel):
    """Enlace a visualizacion interactiva oficial asociada al conjunto."""
    titulo: str
    endpoint: str


class DatasetResourceAnalysisResponse(BaseModel):
    """Respuesta completa con datos procesados en parquet y graficas de un conjunto."""
    dataset: str
    recurso_id: str
    nombre_recurso: str
    formato: str = ""
    ya_estaba_descargado: bool
    ya_estaba_procesado: bool
    ruta_parquet: str
    hojas: List[str] = Field(default_factory=list)
    hoja_actual: Optional[int] = None
    total_filas: int
    total_columnas: int
    completitud_pct: float
    columnas: List[str] = Field(default_factory=list)
    columnas_numericas: List[str] = Field(default_factory=list)
    columnas_categoricas: List[str] = Field(default_factory=list)
    agrupado_por: Optional[str] = None
    metrica_activa: Optional[str] = None
    estadisticas_numericas: List[DatasetColumnStat] = Field(default_factory=list)
    graficas: List[DatasetChartItem] = Field(default_factory=list)
    visualizaciones_curadas: List[CuratedVisualizationLink] = Field(default_factory=list)
    filas_muestra: List[Dict[str, Any]] = Field(default_factory=list)
