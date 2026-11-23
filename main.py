"""Servicio principal de la api balam data systems para ingestion y consulta de datos ine ckan."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from scalar_fastapi import get_scalar_api_reference

from src.ingestion.ine import (
    call_ckan,
    download_resource_file,
    get_dataset_resources,
    has_remote_changed,
    list_all_datasets,
    list_groups,
    query_datastore_sql,
    search_datasets,
    search_datastore
)

app = FastAPI(
    title="Balam Data Systems",
    description="Documentacion de la api para el dataton ine 2026 - balam data systems (bds)",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)


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


# interfaz grafica scalar para explorar la documentacion
@app.get("/docs", include_in_schema=False)
async def scalar_docs():
    """Renderizar interfaz de documentacion con scalar."""
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )


# verificacion del estado de la api
@app.get("/", summary="Estado del servicio")
def home():
    """Verificar que el servicio se encuentra activo."""
    return {"mensaje": "api de balam data systems"}


# buscar conjuntos de datos con filtros y paginacion de 10 por defecto
@app.get("/ine/conjuntos", summary="Buscar conjuntos de datos del ine")
@app.get("/ine/datasets", summary="Buscar conjuntos de datos del ine (alias)", include_in_schema=False)
def get_datasets(
    consulta: Optional[str] = Query(default=None, description="Texto de busqueda para encontrar conjuntos (ej. enei, 2025)"),
    query: Optional[str] = Query(default=None, description="Alias en ingles para compatibilidad"),
    grupo: Optional[str] = Query(default=None, description="Nombre del grupo tematico para filtrar"),
    filas: int = Query(default=10, ge=1, le=1000, description="Cantidad de resultados por pagina"),
    inicio: int = Query(default=0, ge=0, description="Desplazamiento inicial"),
):
    """Consultar conjuntos de datos en ckan por palabra clave, grupo o de forma global."""
    search_term = consulta if consulta is not None else query
    try:
        data = search_datasets(
            query=search_term,
            group=grupo,
            rows=filas,
            start=inicio
        )
        return {
            "consulta": search_term,
            "grupo": grupo,
            "total": data.get("total", 0),
            "inicio": data.get("inicio", 0),
            "filas": data.get("filas", filas),
            "conjuntos": data.get("conjuntos", [])
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al consultar ckan: {exc}")


# listar todos los conjuntos de datos paginando automaticamente con limite de 10 por defecto
@app.get("/ine/todos-los-conjuntos", summary="Obtener catalogo completo de conjuntos")
def get_all_datasets(
    grupo: Optional[str] = Query(default=None, description="Grupo tematico opcional"),
    limite: Optional[int] = Query(default=10, ge=1, description="Limite maximo de conjuntos a recuperar"),
):
    """Recorrer recursivamente las paginas de ckan para extraer los conjuntos."""
    try:
        packages = list_all_datasets(group=grupo, rows_per_page=10, max_total=limite)
        return {
            "grupo": grupo,
            "total_recuperado": len(packages),
            "conjuntos": packages
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al obtener catalogo completo: {exc}")


# listar grupos tematicos disponibles en ckan
@app.get("/ine/grupos", summary="Listar grupos tematicos")
def get_groups():
    """Obtener grupos estadisticos disponibles en la plataforma de datos abiertos."""
    try:
        groups = list_groups()
        return {
            "total": len(groups),
            "grupos": groups
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al obtener grupos: {exc}")


# consultar los recursos de un conjunto de datos especifico
@app.get("/ine/{slug}/recursos", summary="Obtener recursos de un conjunto")
def get_resources(slug: str):
    """Obtener archivos y tablas asociadas a un conjunto de datos mediante su slug."""
    try:
        resource_items = get_dataset_resources(slug)
        return {
            "dataset": slug,
            "total": len(resource_items),
            "recursos": resource_items
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al obtener recursos: {exc}")


# descargar recurso y guardarlo con procedencia en disco
@app.get("/ine/{slug}/descargar/{resource_id}", summary="Descargar recurso por id")
@app.post("/ine/{slug}/descargar/{resource_id}", summary="Descargar recurso por id (post)", include_in_schema=False)
def download_resource(slug: str, resource_id: str):
    """Descargar archivo de datos del ine registrar procedencia y devolverlo."""
    try:
        # primero obtener los recursos del conjunto para localizar el elemento correcto
        resource_list = get_dataset_resources(slug)
        target_resource = next(
            (item for item in resource_list if item.get("id") == resource_id),
            None
        )

        if not target_resource:
            raise HTTPException(
                status_code=404,
                detail=f"recurso con id {resource_id} no encontrado en el conjunto {slug}"
            )

        saved_path = download_resource_file(target_resource)

        if not saved_path.exists():
            raise HTTPException(
                status_code=502,
                detail="el archivo descargado no se encuentra en el almacenamiento local"
            )

        return FileResponse(
            path=str(saved_path),
            filename=saved_path.name,
            media_type="application/octet-stream"
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al descargar recurso: {exc}")


# verificar si un recurso remoto fue modificado comparando el manifest
@app.get("/ine/{slug}/verificar-cambio/{resource_id}", summary="Verificar cambio remoto")
def check_resource_change(slug: str, resource_id: str):
    """Comparar metadatos remotos con la ultima descarga en manifest.jsonl."""
    try:
        resource_list = get_dataset_resources(slug)
        target_resource = next(
            (item for item in resource_list if item.get("id") == resource_id),
            None
        )

        if not target_resource:
            raise HTTPException(
                status_code=404,
                detail=f"recurso con id {resource_id} no encontrado en el conjunto {slug}"
            )

        changed = has_remote_changed(target_resource)
        return {
            "dataset": slug,
            "recurso_id": resource_id,
            "cambio_remoto": changed,
            "ultima_modificacion_remota": target_resource.get("last_modified")
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al verificar cambios: {exc}")


# consultar registros tabulares de un recurso en el datastore de ckan
@app.get("/ine/datastore/consulta", summary="Consultar registros tabulares del datastore")
def get_datastore_records(
    recurso_id: str = Query(..., description="Id del recurso que contiene la tabla"),
    limite: int = Query(default=10, ge=1, le=10000, description="Limite de filas a devolver"),
    desplazamiento: int = Query(default=0, ge=0, description="Desplazamiento de filas"),
    consulta: Optional[str] = Query(default=None, description="Termino de busqueda en texto"),
):
    """Consultar datos tabulares indexados en el datastore de ckan mediante api rest."""
    try:
        result = search_datastore(
            resource_id=recurso_id,
            limit=limite,
            offset=desplazamiento,
            query=consulta
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al consultar datastore: {exc}")


@app.post("/ine/datastore/consulta", summary="Consultar registros tabulares del datastore con cuerpo json")
def post_datastore_records(body: DatastoreSearchBody):
    """Consultar datos tabulares en ckan utilizando un cuerpo de peticion json estructurado."""
    try:
        result = search_datastore(
            resource_id=body.recurso_id,
            limit=body.limite,
            offset=body.desplazamiento,
            query=body.consulta,
            filters=body.filtros,
            sort=body.orden
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al consultar datastore: {exc}")


# consultar el datastore mediante sql
@app.get("/ine/datastore/consulta-sql", summary="Consultar datastore mediante sql")
def get_datastore_sql(
    sql: str = Query(..., description="Sentencia sql (ej. select * from \"<resource_id>\" limit 5)"),
):
    """Ejecutar una consulta sql directa sobre las tablas almacenadas en el datastore."""
    try:
        result = query_datastore_sql(sql=sql)
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al ejecutar consulta sql: {exc}")


@app.post("/ine/datastore/consulta-sql", summary="Consultar datastore mediante sql con json")
def post_datastore_sql(body: SqlQueryBody):
    """Ejecutar una consulta sql en el datastore enviando el cuerpo en formato json."""
    try:
        result = query_datastore_sql(sql=body.sql)
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al ejecutar consulta sql: {exc}")
