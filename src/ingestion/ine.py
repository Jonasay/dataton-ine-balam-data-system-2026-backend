"""Cliente ckan para el portal ine con registro de procedencia y consulta de datastore."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
import requests

load_dotenv()

# configuracion base cargada desde variables de entorno o valor predeterminado
BASE_URL = os.getenv("BASE_PATH_INE", "https://datos.ine.gob.gt/api/3/action").rstrip("/")
RAW_DATA_DIR = Path("data/raw")
DEFAULT_USER_AGENT = "datathon-ine-2026 (equipo: balam-data-systems; contacto: dev@balam.gt)"
DEFAULT_HEADERS = {"User-Agent": DEFAULT_USER_AGENT}
DEFAULT_TIMEOUT = int(os.getenv("INE_REQUEST_TIMEOUT", "60"))


def call_ckan(action: str, timeout: int = DEFAULT_TIMEOUT, **params: Any) -> Any:
    """Ejecutar accion contra la api ckan y validar respuesta."""
    url = f"{BASE_URL}/{action}"
    # limpiar parametros con valor nulo antes de enviar la peticion
    cleaned_params = {k: v for k, v in params.items() if v is not None}
    
    response = requests.get(
        url,
        params=cleaned_params,
        headers=DEFAULT_HEADERS,
        timeout=timeout
    )
    response.raise_for_status()
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


def download_resource_file(
    resource: Dict[str, Any],
    base_dir: Path = RAW_DATA_DIR,
    timeout: int = 300
) -> Path:
    """Descargar un recurso a disco y anotar procedencia en manifest.jsonl."""
    dataset_name = resource.get("dataset", "general")
    target_dir = base_dir / dataset_name
    target_dir.mkdir(parents=True, exist_ok=True)
    
    resource_url = resource.get("url")
    if not resource_url:
        raise ValueError("el recurso no contiene una url valida para descarga")
        
    raw_filename = resource_url.rsplit("/", 1)[-1].split("?")[0]
    # asignar un nombre por defecto si la url termina en barra diagonal
    if not raw_filename:
        res_id = resource.get("id", "recurso")
        res_fmt = resource.get("formato", "bin")
        raw_filename = f"{res_id}.{res_fmt}"
        
    file_path = target_dir / raw_filename
    hasher = hashlib.sha256()
    
    # transmitir el contenido al disco en bloques de 1mb
    with requests.get(resource_url, headers=DEFAULT_HEADERS, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with open(file_path, "wb") as output_file:
            for chunk in response.iter_content(chunk_size=1048576):
                if chunk:
                    output_file.write(chunk)
                    hasher.update(chunk)
                    
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
