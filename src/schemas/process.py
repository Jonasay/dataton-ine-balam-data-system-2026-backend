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


class GeoMapRequest(BaseModel):
    """Modelo para generacion y fusion de mapas geoespaciales."""
    ruta_geo: str = Field(..., description="Ruta del archivo shapefile o geojson en data/raw")
    ruta_parquet: str = Field(..., description="Ruta del archivo parquet en data/processed")
    columna_codigo_geo: str = Field(default="COD_COLUMNA", description="Columna identificadora en la capa geografica")
    columna_codigo_parquet: str = Field(default="cod", description="Columna identificadora en la tabla parquet")
    columna_valor: str = Field(default="valor", description="Columna con los valores cuantitativos a representar")
    columna_nombre: str = Field(default="nombre", description="Columna con la etiqueta de texto para tooltip o hover")
    esquema_color: str = Field(default="Blues", description="Paleta de colores para el mapa coropletico")
    capa_base: str = Field(default="Esri.WorldGrayCanvas", description="Proveedor de mosaicos de fondo (ej. Esri.WorldGrayCanvas, Esri.WorldStreetMap)")
