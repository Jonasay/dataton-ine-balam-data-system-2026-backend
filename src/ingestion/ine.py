from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from src.core.config import (
    BASE_URL_INE,
    DEFAULT_DOWNLOAD_TIMEOUT,
    DEFAULT_HEADERS,
    DEFAULT_REQUEST_TIMEOUT,
    PROCESSED_DATA_DIR,
    RAW_DATA_DIR,
)

# configuracion base importada del modulo core
BASE_URL = BASE_URL_INE
DEFAULT_TIMEOUT = DEFAULT_REQUEST_TIMEOUT


def call_ckan(action: str, timeout: int = DEFAULT_TIMEOUT, **params: Any) -> Any:
    """Ejecutar accion contra la api ckan con reintentos ante fallos transitorios y validar respuesta."""
    url = f"{BASE_URL}/{action}"
    # limpiar parametros con valor nulo antes de enviar la peticion
    cleaned_params = {k: v for k, v in params.items() if v is not None}

    effective_timeout = min(timeout, 25) if action in {"package_search", "package_show", "group_list"} else timeout
    max_attempts = 2
    response = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(
                url,
                params=cleaned_params,
                headers=DEFAULT_HEADERS,
                timeout=effective_timeout
            )
            response.raise_for_status()
            break
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            # no reintentar errores de cliente (ej. 400, 404)
            if status_code is not None and status_code < 500:
                raise
            if attempt >= max_attempts:
                raise
            time.sleep(0.5 * attempt)
        except requests.RequestException:
            if attempt >= max_attempts:
                raise
            time.sleep(0.5 * attempt)

    payload = response.json()

    if not payload.get("success"):
        error_detail = payload.get("error", "error desconocido en ckan")
        raise RuntimeError(f"ckan devolvio error en accion {action}: {error_detail}")

    return payload["result"]


def search_datasets(
    query: Optional[str] = None,
    group: Optional[str] = None,
    rows: int = 10,
    start: int = 0
) -> Dict[str, Any]:
    """Buscar conjuntos de datos en ckan con paginacion y filtros."""
    params: Dict[str, Any] = {
        "rows": rows,
        "start": start
    }
    
    if query:
        params["q"] = query
    else:
        params["q"] = "*:*"
        
    if group:
        params["fq"] = f"groups:{group}"
        
    raw_result = call_ckan("package_search", **params)
    
    # normalizar la estructura de los conjuntos recibidos
    normalized_items: List[Dict[str, Any]] = []
    for package in raw_result.get("results", []):
        normalized_items.append({
            "id": package.get("name"),
            "nombre": package.get("title"),
            "descripcion": package.get("notes") or "",
            "autor": package.get("author") or "",
            "organizacion": (package.get("organization") or {}).get("title", ""),
            "modificado": package.get("metadata_modified"),
            "recursos_total": len(package.get("resources", [])),
            "recursos": [
                {
                    "id": res.get("id"),
                    "nombre": res.get("name"),
                    "formato": (res.get("format") or "").lower(),
                    "url": res.get("url"),
                    "modificado": res.get("last_modified") or res.get("metadata_modified")
                }
                for res in package.get("resources", [])
            ]
        })
        
    return {
        "total": raw_result.get("count", 0),
        "inicio": start,
        "filas": rows,
        "conjuntos": normalized_items
    }


def list_all_datasets(
    group: Optional[str] = None,
    rows_per_page: int = 10,
    pause_seconds: float = 0.5,
    max_total: Optional[int] = 10
) -> List[Dict[str, Any]]:
    """Paginar recursivamente package_search y devolver metadatos de los conjuntos."""
    all_packages: List[Dict[str, Any]] = []
    current_offset = 0
    
    while True:
        search_data = search_datasets(
            query=None,
            group=group,
            rows=rows_per_page,
            start=current_offset
        )
        batch = search_data.get("conjuntos", [])
        all_packages.extend(batch)
        
        total_available = search_data.get("total", 0)
        current_offset += rows_per_page
        
        # salir al agotar resultados disponibles o alcanzar el limite maximo
        if current_offset >= total_available:
            break
        if max_total and len(all_packages) >= max_total:
            all_packages = all_packages[:max_total]
            break
            
        # pausa de cortesia entre llamadas a la api
        time.sleep(pause_seconds)
        
    return all_packages


def get_dataset_resources(slug: str) -> List[Dict[str, Any]]:
    """Obtener lista de recursos de un conjunto especifico usando package_show."""
    package = call_ckan("package_show", id=slug)
    dataset_modified = package.get("metadata_modified")
    license_id = package.get("license_id")
    
    resource_list: List[Dict[str, Any]] = []
    for res in package.get("resources", []):
        resource_list.append({
            "id": res.get("id"),
            "nombre": res.get("name"),
            "formato": (res.get("format") or "").lower(),
            "url": res.get("url"),
            "last_modified": res.get("last_modified") or res.get("metadata_modified"),
            "dataset": slug,
            "dataset_modified": dataset_modified,
            "license": license_id
        })
        
    return resource_list


def resolve_local_resource_path(
    resource: Dict[str, Any],
    base_dir: Path = RAW_DATA_DIR,
) -> Path:
    """Construir ruta local determinista donde se almacena un recurso de ckan."""
    dataset_name = resource.get("dataset") or "general"
    target_dir = base_dir / dataset_name

    resource_url = resource.get("url") or ""
    raw_filename = resource_url.rsplit("/", 1)[-1].split("?")[0] if resource_url else ""
    if not raw_filename:
        res_id = resource.get("id") or "recurso"
        res_fmt = (resource.get("formato") or resource.get("format") or "bin").lower()
        raw_filename = f"{res_id}.{res_fmt}"

    return target_dir / raw_filename


def _read_manifest_entries(base_dir: Path = RAW_DATA_DIR) -> List[Dict[str, Any]]:
    """Leer registros de auditoria del manifiesto local si existe."""
    manifest_file = base_dir / "manifest.jsonl"
    if not manifest_file.exists():
        return []
    entries: List[Dict[str, Any]] = []
    for line in manifest_file.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean:
            continue
        try:
            entries.append(json.loads(clean))
        except json.JSONDecodeError:
            continue
    return entries


def get_local_resource_status(
    resource: Dict[str, Any],
    base_dir: Path = RAW_DATA_DIR,
    processed_dir: Path = PROCESSED_DATA_DIR,
) -> Dict[str, Any]:
    """Verificar si un recurso ya fue descargado y si cuenta con parquet procesado local."""
    dataset_slug = resource.get("dataset") or "general"
    local_path = resolve_local_resource_path(resource, base_dir=base_dir)
    file_exists = local_path.exists() and local_path.is_file() and local_path.stat().st_size > 0
    file_size = local_path.stat().st_size if file_exists else None

    # revisar si el archivo en manifiesto tuvo modificacion remota respecto a la descarga previa
    remote_modified = resource.get("last_modified") or resource.get("modificado")
    matched = [rec for rec in _read_manifest_entries(base_dir) if rec.get("id") == resource.get("id")]
    remote_changed = False
    if matched and remote_modified:
        last_known = matched[-1].get("last_modified") or matched[-1].get("modificado")
        if last_known and last_known != remote_modified:
            remote_changed = True

    # verificar existencia de parquet procesado para este recurso
    parquet_dir = processed_dir / "datasets" / dataset_slug
    stem = local_path.stem
    parquet_candidates = sorted(parquet_dir.glob(f"{stem}*.parquet")) if parquet_dir.exists() else []
    parquet_path = parquet_candidates[0] if parquet_candidates else None

    is_ready_locally = file_exists and not remote_changed
    return {
        "descargado_local": is_ready_locally,
        "archivo_existe": file_exists,
        "ruta_local": str(local_path) if file_exists else None,
        "tamano_bytes": file_size,
        "cambio_remoto": remote_changed if file_exists else True,
        "requiere_descarga": not is_ready_locally,
        "parquet_disponible": parquet_path is not None and parquet_path.exists(),
        "ruta_parquet": str(parquet_path.relative_to(processed_dir)) if parquet_path else None,
    }


def download_resource_file(
    resource: Dict[str, Any],
    base_dir: Path = RAW_DATA_DIR,
    timeout: int = DEFAULT_DOWNLOAD_TIMEOUT,
    max_retries: int = 4
) -> Path:
    """Descargar un recurso a disco con reintentos automaticos y anotar procedencia en manifest.jsonl."""
    resource_url = resource.get("url")
    if not resource_url:
        raise ValueError("el recurso no contiene una url valida para descarga")

    file_path = resolve_local_resource_path(resource, base_dir=base_dir)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = file_path.parent / f"{file_path.name}.part"
    
    last_err: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        hasher = hashlib.sha256()
        try:
            with requests.get(resource_url, headers=DEFAULT_HEADERS, stream=True, timeout=timeout) as response:
                response.raise_for_status()
                with open(temp_file, "wb") as output_file:
                    for chunk in response.iter_content(chunk_size=1048576):
                        if chunk:
                            output_file.write(chunk)
                            hasher.update(chunk)
                            
            # si finalizo correctamente, mover el archivo temporal al destino definitivo
            if temp_file.exists():
                temp_file.replace(file_path)
            last_err = None
            break
        except Exception as exc:
            last_err = exc
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            if attempt < max_retries:
                time.sleep(2 * attempt)
            else:
                raise RuntimeError(f"Fallo descarga de {resource_url} tras {max_retries} intentos: {exc}") from exc
                
    # agregar registro de auditoria al archivo manifest
    manifest_record = {
        **resource,
        "ruta_local": str(file_path),
        "sha256": hasher.hexdigest(),
        "bytes": file_path.stat().st_size,
        "descargado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fuente": "instituto nacional de estadistica (ine), datos.ine.gob.gt"
    }
    
    manifest_file = base_dir / "manifest.jsonl"
    with open(manifest_file, "a", encoding="utf-8") as manifest_handle:
        manifest_handle.write(json.dumps(manifest_record, ensure_ascii=False) + "\n")
        
    return file_path


def has_remote_changed(resource: Dict[str, Any], base_dir: Path = RAW_DATA_DIR) -> bool:
    """Verificar si el recurso ha cambiado remotamente comparando manifest local."""
    manifest_file = base_dir / "manifest.jsonl"
    if not manifest_file.exists():
        return True
        
    lines = manifest_file.read_text(encoding="utf-8").strip().splitlines()
    records = [json.loads(line) for line in lines if line.strip()]
    matched_records = [rec for rec in records if rec.get("id") == resource.get("id")]
    
    if not matched_records:
        return True
        
    # comparar la fecha de ultima modificacion remota
    last_known_entry = matched_records[-1]
    return last_known_entry.get("last_modified") != resource.get("last_modified")


def search_datastore(
    resource_id: str,
    limit: int = 10,
    offset: int = 0,
    query: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    sort: Optional[str] = None
) -> Dict[str, Any]:
    """Consultar registros tabulares mediante accion datastore_search."""
    params: Dict[str, Any] = {
        "resource_id": resource_id,
        "limit": limit,
        "offset": offset
    }
    
    if query:
        params["q"] = query
        
    if filters:
        params["filters"] = json.dumps(filters)
        
    if sort:
        params["sort"] = sort
        
    raw_result = call_ckan("datastore_search", **params)
    return {
        "resource_id": resource_id,
        "total": raw_result.get("total", 0),
        "campos": raw_result.get("fields", []),
        "registros": raw_result.get("records", []),
        "limite": limit,
        "desplazamiento": offset
    }


def query_datastore_sql(sql: str) -> Dict[str, Any]:
    """Consultar el datastore de ckan mediante sentencia sql."""
    raw_result = call_ckan("datastore_search_sql", sql=sql)
    return {
        "campos": raw_result.get("fields", []),
        "registros": raw_result.get("records", [])
    }


def list_groups() -> List[Dict[str, Any]]:
    """Obtener lista de grupos tematicos disponibles en el catalogo ckan."""
    raw_groups = call_ckan("group_list", all_fields=True)
    return [
        {
            "id": group.get("id"),
            "nombre": group.get("name"),
            "titulo": group.get("title"),
            "descripcion": group.get("description") or "",
            "total_paquetes": group.get("package_count", 0)
        }
        for group in raw_groups
    ]


# alias para compatibilidad y uso flexible
ckan = call_ckan
datasets = search_datasets
resources = get_dataset_resources
download = download_resource_file
listar_conjuntos = list_all_datasets
recursos = get_dataset_resources
descargar = download_resource_file
cambio_remoto = has_remote_changed
consulta_datastore = search_datastore
consulta_sql = query_datastore_sql
