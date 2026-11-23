from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from src.core.config import RAW_DATA_DIR
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
from src.process.process import _require_polars, read_excel_sheets
from src.schemas.ine import DatastoreSearchBody, SqlQueryBody

router = APIRouter(
    prefix="/ine",
    tags=["INE - Instituto Nacional de Estadistica"]
)


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


# listar grupos tematicos disponibles en ckan
@router.get("/grupos", summary="Listar grupos tematicos")
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
@router.get("/{slug}/recursos", summary="Obtener recursos de un conjunto")
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


# previsualizar datos directamente por slug o recurso sin necesidad de descarga manual
@router.get("/{slug}/vista-previa", summary="Previsualizar datos de un dataset directamente")
@router.get("/{slug}/preview", summary="Previsualizar datos de un dataset (alias)", include_in_schema=False)
@router.get("/{slug}/recursos/{resource_id}/vista-previa", summary="Previsualizar recurso especifico", include_in_schema=False)
def preview_dataset_data(
    slug: str,
    recurso_id: Optional[str] = Query(default=None, description="Id del recurso especifico (opcional)"),
    resource_id: Optional[str] = Query(default=None, description="Alias en ingles de recurso_id", include_in_schema=False),
    hoja_id: int = Query(default=1, ge=0, description="Indice o numero de hoja de excel a previsualizar"),
    limite: int = Query(default=10, ge=1, le=1000, description="Cantidad maxima de filas para vista previa"),
):
    """Previsualizar registros y estructura de un conjunto del ine sin requerir descarga manual previa ni rutas locales."""
    try:
        resources = get_dataset_resources(slug)
        if not resources:
            raise HTTPException(status_code=404, detail=f"no se encontraron recursos para el conjunto {slug}")

        target_id = recurso_id or resource_id
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

        # intentar primero obtener registros indexados directamente del datastore ckan
        try:
            datastore_data = search_datastore(resource_id=active_id, limit=limite)
            records = datastore_data.get("records", [])
            if records:
                fields = [f.get("id") for f in datastore_data.get("fields", [])]
                return {
                    "dataset": slug,
                    "recurso_id": active_id,
                    "nombre": target_resource.get("nombre"),
                    "formato": target_resource.get("formato"),
                    "origen": "datastore_ckan",
                    "hojas": [],
                    "hoja_actual": None,
                    "columnas": fields,
                    "filas_muestra": records,
                    "total_filas_muestra": len(records)
                }
        except Exception:
            # continuar con lectura de archivo si el recurso no esta indexado en datastore
            pass

        # descarga transparente si el archivo aun no esta en almacenamiento local
        file_name = target_resource["url"].rsplit("/", 1)[-1]
        local_path = RAW_DATA_DIR / slug / file_name
        if not local_path.exists():
            local_path = download_resource_file(target_resource)

        # procesar y extraer vista previa segun la extension
        file_ext = local_path.suffix.lower()
        if file_ext in [".xlsx", ".xls"]:
            # inspeccionar nombres de hojas
            sheets_dict = read_excel_sheets(local_path, sheet_id=0)
            sheet_names = list(sheets_dict.keys()) if isinstance(sheets_dict, dict) else []

            # leer datos de la hoja solicitada
            sheet_df = read_excel_sheets(local_path, sheet_id=hoja_id)
            preview_rows = sheet_df.head(limite).to_dicts()
            return {
                "dataset": slug,
                "recurso_id": active_id,
                "nombre": target_resource.get("nombre"),
                "formato": target_resource.get("formato", "xlsx"),
                "origen": "archivo_local_autodescargado",
                "archivo": local_path.name,
                "hojas": sheet_names,
                "hoja_actual": hoja_id,
                "columnas": sheet_df.columns,
                "filas_muestra": preview_rows,
                "total_filas_muestra": len(preview_rows)
            }
        elif file_ext == ".csv":
            pl = _require_polars()
            df = pl.read_csv(str(local_path), n_rows=limite)
            preview_rows = df.head(limite).to_dicts()
            return {
                "dataset": slug,
                "recurso_id": active_id,
                "nombre": target_resource.get("nombre"),
                "formato": "csv",
                "origen": "archivo_local_autodescargado",
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


# descargar recurso y guardarlo con procedencia en disco
@router.get("/{slug}/descargar/{resource_id}", summary="Descargar recurso por id")
@router.post("/{slug}/descargar/{resource_id}", summary="Descargar recurso por id (post)", include_in_schema=False)
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
@router.get("/{slug}/verificar-cambio/{resource_id}", summary="Verificar cambio remoto")
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
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al consultar datastore: {exc}")


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
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al consultar datastore: {exc}")


# consultar el datastore mediante sql
@router.get("/datastore/consulta-sql", summary="Consultar datastore mediante sql")
def get_datastore_sql(
    sql: str = Query(..., description="Sentencia sql (ej. select * from \"<resource_id>\" limit 5)"),
):
    """Ejecutar una consulta sql directa sobre las tablas almacenadas en el datastore."""
    try:
        result = query_datastore_sql(sql=sql)
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al ejecutar consulta sql: {exc}")


@router.post("/datastore/consulta-sql", summary="Consultar datastore mediante sql con json")
def post_datastore_sql(body: SqlQueryBody):
    """Ejecutar una consulta sql en el datastore enviando el cuerpo en formato json."""
    try:
        result = query_datastore_sql(sql=body.sql)
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al ejecutar consulta sql: {exc}")
