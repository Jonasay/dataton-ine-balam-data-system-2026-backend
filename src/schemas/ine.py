from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class DatastoreSearchBody(BaseModel):
    """Modelo para busqueda en datastore mediante cuerpo json."""
    recurso_id: str = Field(..., description="Identificador unico del recurso en ckan")
    limite: int = Field(default=10, ge=1, le=10000, description="Cantidad maxima de registros a devolver")
    desplazamiento: int = Field(default=0, ge=0, description="Numero de registros a omitir para paginacion")
    consulta: Optional[str] = Field(default=None, description="Texto para filtrar coincidencias en los campos")
    filtros: Optional[Dict[str, Any]] = Field(default=None, description="Diccionario de filtros por columna")
    orden: Optional[str] = Field(default=None, description="Campo para ordenar resultados")


class SqlQueryBody(BaseModel):
    """Modelo para ejecucion de consultas sql sobre el datastore."""
    sql: str = Field(..., description="Sentencia sql compatible con ckan datastore")
