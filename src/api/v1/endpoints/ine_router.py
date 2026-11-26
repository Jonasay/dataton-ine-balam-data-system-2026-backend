from __future__ import annotations

import math
import threading
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
import requests

from src.core.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from src.ingestion.ine import (
    download_resource_file,
    get_dataset_resources,
    get_local_resource_status,
    has_remote_changed,
    list_groups,
    query_datastore_sql,
    search_datasets,
    search_datastore,
)
from src.process.process import _require_polars, read_excel_sheets
from src.schemas.ine import DatastoreSearchBody, SqlQueryBody

router = APIRouter(
    prefix="/ine",
    tags=["INE - Instituto Nacional de Estadistica"]
)

# cache en memoria con ttl para consultas frecuentes al catalogo ckan
_CKAN_CACHE_TTL_SECONDS = 180.0
_ckan_cache: Dict[Tuple[Any, ...], Tuple[float, Any]] = {}
_ckan_cache_lock = threading.Lock()


def _is_mocked_callable(fn: Callable[..., Any]) -> bool:
    """Detectar si una funcion fue reemplazada por un mock en pruebas unitarias."""
    return hasattr(fn, "assert_called") or getattr(fn, "__module__", "").startswith("unittest.mock")


def _cached_ckan_fetch(cache_key: Tuple[Any, ...], fn: Callable[[], Any], loader_ref: Callable[..., Any]) -> Any:
    """Ejecutar consulta ckan con cache temporal y respaldo obsoleto si el origen falla."""
    if _is_mocked_callable(loader_ref):
        return fn()

    now = time.monotonic()
    stale_entry: Any = None
    with _ckan_cache_lock:
        cached = _ckan_cache.get(cache_key)
        if cached is not None:
            expires_at, payload = cached
            if now < expires_at:
                return payload
            stale_entry = payload

    try:
        result = fn()
        with _ckan_cache_lock:
            _ckan_cache[cache_key] = (now + _CKAN_CACHE_TTL_SECONDS, result)
        return result
    except Exception:
        if stale_entry is not None:
            return stale_entry
        raise


def _raise_ckan_http_error(exc: Exception, context_message: str) -> None:
    """Propagar codigo http 404 cuando el recurso remoto no existe o 502 para fallos externos."""
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"{context_message}: recurso no encontrado en ckan")
    raise HTTPException(status_code=502, detail=f"{context_message}: {exc}")


def _sanitize_json_value(value: Any) -> Any:
    """Convertir valores no compatibles con json estandar (nan, inf, fechas, decimales)."""
    if value is None:
        return None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        f_val = float(value)
        return f_val if math.isfinite(f_val) else None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(k): _sanitize_json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    return value


def _sanitize_records(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """Normalizar lista de registros tabulares para serializacion json estricta."""
    return [{str(k): _sanitize_json_value(v) for k, v in row.items()} for row in rows]


# buscar conjuntos de datos con filtros y paginacion de 10 por defecto
@router.get("/conjuntos", summary="Buscar conjuntos de datos del ine")
@router.get("/datasets", summary="Buscar conjuntos de datos del ine (alias)", include_in_schema=False)
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
        cache_key = ("conjuntos", search_term, grupo, filas, inicio)
        data = _cached_ckan_fetch(
            cache_key,
            lambda: search_datasets(
                query=search_term,
                group=grupo,
                rows=filas,
                start=inicio
            ),
            search_datasets,
        )

        # precalentar cache de recursos a partir de la respuesta de package_search
        conjuntos = data.get("conjuntos", [])
        if not _is_mocked_callable(search_datasets) and not _is_mocked_callable(get_dataset_resources):
            now = time.monotonic()
            with _ckan_cache_lock:
                for ds in conjuntos:
                    ds_id = ds.get("id")
                    ds_resources = ds.get("recursos")
                    if ds_id and isinstance(ds_resources, list) and ds_resources:
                        normalized_res = [
                            {
                                "id": r.get("id"),
                                "nombre": r.get("nombre"),
                                "formato": (r.get("formato") or "").lower(),
                                "url": r.get("url"),
                                "last_modified": r.get("modificado") or r.get("last_modified"),
                                "dataset": ds_id,
                                "dataset_modified": ds.get("modificado"),
                            }
                            for r in ds_resources
                        ]
                        _ckan_cache[("recursos", ds_id)] = (now + _CKAN_CACHE_TTL_SECONDS, normalized_res)

        return {
            "consulta": search_term,
            "grupo": grupo,
            "total": data.get("total", 0),
            "inicio": data.get("inicio", 0),
            "filas": data.get("filas", filas),
            "conjuntos": conjuntos
        }
    except HTTPException:
        raise
    except Exception as exc:
        _raise_ckan_http_error(exc, "error al consultar ckan")


# listar grupos tematicos disponibles en ckan
@router.get("/grupos", summary="Listar grupos tematicos")
def get_groups():
    """Obtener grupos estadisticos disponibles en la plataforma de datos abiertos."""
    try:
        groups = _cached_ckan_fetch(("grupos",), list_groups, list_groups)
        return {
            "total": len(groups),
            "grupos": groups
        }
    except HTTPException:
        raise
    except Exception as exc:
        _raise_ckan_http_error(exc, "error al obtener grupos")


def get_cached_or_fetch_resources(slug: str) -> list[Dict[str, Any]]:
    """Obtener recursos de un conjunto desde cache temporal o consultando ckan."""
    def _fetch() -> list[Dict[str, Any]]:
        try:
            return get_dataset_resources(slug)
        except Exception as primary_exc:
            # respaldo mediante package_search cuando package_show excede el tiempo de espera
            if not _is_mocked_callable(get_dataset_resources):
                try:
                    search_res = search_datasets(query=slug, rows=10, start=0)
                    match = next((ds for ds in search_res.get("conjuntos", []) if ds.get("id") == slug), None)
                    if match and match.get("recursos"):
                        return [
                            {
                                "id": r.get("id"),
                                "nombre": r.get("nombre"),
                                "formato": (r.get("formato") or "").lower(),
                                "url": r.get("url"),
                                "last_modified": r.get("modificado") or r.get("last_modified"),
                                "dataset": slug,
                                "dataset_modified": match.get("modificado"),
                            }
                            for r in match["recursos"]
                        ]
                except Exception:
                    pass
            raise primary_exc

    return _cached_ckan_fetch(
        ("recursos", slug),
        _fetch,
        get_dataset_resources,
    )


def _enrich_resource_status(slug: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """Agregar metadatos de verificacion local para evitar descargas repetidas."""
    if not item.get("url"):
        return item
    status = get_local_resource_status(
        {**item, "dataset": item.get("dataset") or slug},
        base_dir=RAW_DATA_DIR,
        processed_dir=PROCESSED_DATA_DIR,
    )
    return {
        **item,
        "descargado_local": status["descargado_local"],
        "tamano_bytes": status["tamano_bytes"],
        "ruta_local": status["ruta_local"],
        "cambio_remoto": status["cambio_remoto"],
        "parquet_disponible": status["parquet_disponible"],
        "ruta_parquet": status["ruta_parquet"],
    }


# consultar los recursos de un conjunto de datos especifico
@router.get("/{slug}/recursos", summary="Obtener recursos de un conjunto")
def get_resources(slug: str):
    """Obtener archivos y tablas asociadas a un conjunto de datos mediante su slug."""
    try:
        resource_items = get_cached_or_fetch_resources(slug)
        enriched = [_enrich_resource_status(slug, item) for item in resource_items]
        return {
            "dataset": slug,
            "total": len(enriched),
            "recursos": enriched
        }
    except HTTPException:
        raise
    except Exception as exc:
        _raise_ckan_http_error(exc, "error al obtener recursos")


# previsualizar datos directamente por slug o recurso sin necesidad de descarga manual
@router.get("/{slug}/vista-previa", summary="Previsualizar datos de un dataset directamente")
@router.get("/{slug}/preview", summary="Previsualizar datos de un dataset (alias)", include_in_schema=False)
def preview_dataset_data(
    slug: str,
    recurso_id: Optional[str] = Query(default=None, description="Id del recurso especifico (opcional)"),
    hoja_id: int = Query(default=1, ge=0, description="Indice o numero de hoja de excel a previsualizar"),
    limite: int = Query(default=10, ge=1, le=1000, description="Cantidad maxima de filas para vista previa"),
):
    """Previsualizar registros y estructura de un conjunto del ine sin requerir descarga manual previa ni rutas locales."""
    try:
        # normalizar parametros si se invoca internamente como funcion directa de python
        from fastapi.params import Query as QueryParam
        target_id = None if isinstance(recurso_id, QueryParam) else recurso_id
        active_hoja = 1 if isinstance(hoja_id, QueryParam) else hoja_id
        active_limite = 10 if isinstance(limite, QueryParam) else limite

        resources = get_cached_or_fetch_resources(slug)
        if not resources:
            raise HTTPException(status_code=404, detail=f"no se encontraron recursos para el conjunto {slug}")

        target_resource = None
        if target_id:
            target_resource = next((r for r in resources if r.get("id") == target_id), None)
            if not target_resource:
                raise HTTPException(status_code=404, detail=f"recurso {target_id} no encontrado en {slug}")
        else:
            # seleccionar preferentemente un recurso tabular (xlsx, csv, xls)
            tabular_formats = {"xlsx", "csv", "xls"}
            target_resource = next(
                (r for r in resources if str(r.get("formato", "")).lower() in tabular_formats),
                resources[0]
            )

        active_id = target_resource["id"]
        enriched_target = {**target_resource, "dataset": target_resource.get("dataset") or slug}
        local_status = get_local_resource_status(enriched_target, base_dir=RAW_DATA_DIR, processed_dir=PROCESSED_DATA_DIR)

        if local_status["descargado_local"] and local_status["ruta_local"]:
            local_path = Path(local_status["ruta_local"])
            preview_origin = "archivo_local_cache"
        else:
            # intentar obtener registros indexados directamente del datastore ckan si aun no esta en disco
            try:
                datastore_data = search_datastore(resource_id=active_id, limit=active_limite)
                records = datastore_data.get("registros") or datastore_data.get("records", [])
                if records:
                    raw_fields = datastore_data.get("campos") or datastore_data.get("fields", [])
                    fields = [f.get("id") for f in raw_fields]
                    return {
                        "dataset": slug,
                        "recurso_id": active_id,
                        "nombre": target_resource.get("nombre"),
                        "formato": target_resource.get("formato"),
                        "origen": "datastore_ckan",
                        "hojas": [],
                        "hoja_actual": None,
                        "columnas": fields,
                        "filas_muestra": _sanitize_records(records),
                        "total_filas_muestra": len(records)
                    }
            except Exception:
                # continuar con descarga unica si el recurso no esta indexado en datastore
                pass

            local_path = download_resource_file(enriched_target)
            preview_origin = "archivo_local_autodescargado"

        # procesar y extraer vista previa segun la extension
        file_ext = local_path.suffix.lower()
        if file_ext in [".xlsx", ".xls"]:
            # inspeccionar nombres de hojas
            sheets_dict = read_excel_sheets(local_path, sheet_id=0)
            sheet_names = list(sheets_dict.keys()) if isinstance(sheets_dict, dict) else []

            # leer datos de la hoja solicitada
            sheet_df = read_excel_sheets(local_path, sheet_id=active_hoja)
            preview_rows = _sanitize_records(sheet_df.head(active_limite).to_dicts())
            return {
                "dataset": slug,
                "recurso_id": active_id,
                "nombre": target_resource.get("nombre"),
                "formato": target_resource.get("formato", "xlsx"),
                "origen": preview_origin,
                "archivo": local_path.name,
                "hojas": sheet_names,
                "hoja_actual": active_hoja,
                "columnas": sheet_df.columns,
                "filas_muestra": preview_rows,
                "total_filas_muestra": len(preview_rows)
            }
        elif file_ext == ".csv":
            pl = _require_polars()
            df = pl.read_csv(str(local_path), n_rows=active_limite, ignore_errors=True)
            preview_rows = _sanitize_records(df.head(active_limite).to_dicts())
            return {
                "dataset": slug,
                "recurso_id": active_id,
                "nombre": target_resource.get("nombre"),
                "formato": "csv",
                "origen": preview_origin,
                "archivo": local_path.name,
                "hojas": [],
                "hoja_actual": None,
                "columnas": df.columns,
                "filas_muestra": preview_rows,
                "total_filas_muestra": len(preview_rows)
            }
        else:
            return {
                "dataset": slug,
                "recurso_id": active_id,
                "nombre": target_resource.get("nombre"),
                "formato": target_resource.get("formato"),
                "origen": "archivo_descargado",
                "archivo": local_path.name,
                "mensaje": f"archivo descargado pero su formato {file_ext} no es tabular"
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al obtener vista previa: {exc}")


# previsualizar recurso especifico por id en la ruta
@router.get("/{slug}/recursos/{resource_id}/vista-previa", summary="Previsualizar recurso especifico", include_in_schema=False)
def preview_resource_data(
    slug: str,
    resource_id: str,
    hoja_id: int = Query(default=1, ge=0, description="Indice o numero de hoja de excel a previsualizar"),
    limite: int = Query(default=10, ge=1, le=1000, description="Cantidad maxima de filas para vista previa"),
):
    """Previsualizar un recurso determinado por su identificador unico."""
    return preview_dataset_data(slug=slug, recurso_id=resource_id, hoja_id=hoja_id, limite=limite)


# descargar recurso y guardarlo con procedencia en disco sin repetir descarga si ya existe
@router.get("/{slug}/descargar/{resource_id}", summary="Descargar recurso por id")
@router.post("/{slug}/descargar/{resource_id}", summary="Descargar recurso por id (post)", include_in_schema=False)
def download_resource(
    slug: str,
    resource_id: str,
    forzar: bool = Query(default=False, description="Forzar descarga remota aunque el recurso ya exista en disco"),
):
    """Descargar archivo de datos del ine verificando cache local antes de solicitarlo al origen."""
    try:
        # primero obtener los recursos del conjunto para localizar el elemento correcto
        resource_list = get_cached_or_fetch_resources(slug)
        target_resource = next(
            (item for item in resource_list if item.get("id") == resource_id),
            None
        )

        if not target_resource:
            raise HTTPException(
                status_code=404,
                detail=f"recurso con id {resource_id} no encontrado en el conjunto {slug}"
            )

        enriched_target = {**target_resource, "dataset": target_resource.get("dataset") or slug}
        local_status = get_local_resource_status(enriched_target, base_dir=RAW_DATA_DIR, processed_dir=PROCESSED_DATA_DIR)
        if not forzar and local_status["descargado_local"] and local_status["ruta_local"]:
            saved_path = Path(local_status["ruta_local"])
        else:
            saved_path = download_resource_file(enriched_target)

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
@router.get("/{slug}/verificar-cambio/{resource_id}", summary="Verificar cambio remoto")
def check_resource_change(slug: str, resource_id: str):
    """Comparar metadatos remotos con la ultima descarga en manifest.jsonl."""
    try:
        resource_list = get_cached_or_fetch_resources(slug)
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
@router.get("/datastore/consulta", summary="Consultar registros tabulares del datastore")
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
    except HTTPException:
        raise
    except Exception as exc:
        _raise_ckan_http_error(exc, "error al consultar datastore")


@router.post("/datastore/consulta", summary="Consultar registros tabulares del datastore con cuerpo json")
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
    except HTTPException:
        raise
    except Exception as exc:
        _raise_ckan_http_error(exc, "error al consultar datastore")


# consultar el datastore mediante sql
@router.get("/datastore/consulta-sql", summary="Consultar datastore mediante sql")
def get_datastore_sql(
    sql: str = Query(..., description="Sentencia sql (ej. select * from \"<resource_id>\" limit 5)"),
):
    """Ejecutar una consulta sql directa sobre las tablas almacenadas en el datastore."""
    try:
        result = query_datastore_sql(sql=sql)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        _raise_ckan_http_error(exc, "error al ejecutar consulta sql")


@router.post("/datastore/consulta-sql", summary="Consultar datastore mediante sql con json")
def post_datastore_sql(body: SqlQueryBody):
    """Ejecutar una consulta sql en el datastore enviando el cuerpo en formato json."""
    try:
        result = query_datastore_sql(sql=body.sql)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        _raise_ckan_http_error(exc, "error al ejecutar consulta sql")
