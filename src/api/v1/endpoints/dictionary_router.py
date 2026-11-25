from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.ingestion.ine import get_dataset_resources, search_datastore
from src.schemas.dictionary import DictionaryTermRequest, DictionaryTranslationRequest
from src.services.dictionary import (
    SUPPORTED_LANGUAGES,
    normalize_term,
    read_entries,
    update_translation,
    upsert_term,
)

router = APIRouter(prefix="/diccionario", tags=["Diccionario - Idiomas Mayas"])


@router.get("/idiomas")
def get_languages():
    """Listar idiomas disponibles y sus códigos."""
    return {"idiomas": [{"codigo": code, "nombre": name} for code, name in SUPPORTED_LANGUAGES.items()]}


@router.get("")
def list_dictionary(
    consulta: Optional[str] = Query(default=None, max_length=200),
    idioma: Optional[str] = Query(default=None),
    solo_validados: bool = Query(default=False),
    limite: int = Query(default=100, ge=1, le=1000),
    inicio: int = Query(default=0, ge=0),
):
    """Buscar términos en el diccionario, opcionalmente por idioma."""
    if idioma and idioma not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail="código de idioma no soportado")
    entries = read_entries()
    query = normalize_term(consulta) if consulta else None
    matched = []
    for entry in entries:
        if query and query not in normalize_term(entry["termino_es"]):
            translation = entry.get("traducciones", {}).get(idioma or "", {}).get("texto", "")
            if query not in normalize_term(translation):
                continue
        if idioma and idioma != "es" and idioma not in entry.get("traducciones", {}):
            continue
        if solo_validados and idioma and idioma != "es":
            translation = entry.get("traducciones", {}).get(idioma, {})
            if not translation.get("validado", False):
                continue
        matched.append(entry)
    return {"total": len(matched), "inicio": inicio, "limite": limite, "terminos": matched[inicio:inicio + limite]}


@router.post("", status_code=201)
def create_dictionary_term(body: DictionaryTermRequest):
    """Agregar un término al diccionario para edición posterior."""
    try:
        return upsert_term(body.termino_es, definition_es=body.definicion_es)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/{term}/traducciones/{language}")
def put_translation(term: str, language: str, body: DictionaryTranslationRequest):
    """Agregar o corregir una traducción. La validación queda registrada explícitamente."""
    try:
        entry = update_translation(term, language, body.traduccion, validated=body.validado)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if entry is None:
        raise HTTPException(status_code=404, detail="término no encontrado")
    return entry


@router.post("/importar/{dataset_slug}")
def import_dataset_terms(
    dataset_slug: str,
    max_resources: int = Query(default=10, ge=1, le=50),
    max_records: int = Query(default=200, ge=1, le=1000),
    max_terms: int = Query(default=1000, ge=1, le=10000),
):
    """Importar encabezados y valores de texto del datastore CKAN como términos pendientes."""
    try:
        resources = get_dataset_resources(dataset_slug)
        imported = 0
        scanned = 0
        errors = []
        for resource in resources[:max_resources]:
            if imported >= max_terms:
                break
            try:
                data = search_datastore(resource_id=resource["id"], limit=max_records)
            except Exception as exc:
                errors.append({"recurso_id": resource.get("id"), "error": str(exc)})
                continue

            terms = []
            for field in data.get("campos", []):
                name = field.get("id")
                if isinstance(name, str):
                    terms.append((name, "campo"))
            for row in data.get("registros", []):
                for field, value in row.items():
                    if isinstance(value, str) and value.strip() and len(value.strip()) <= 200:
                        terms.append((value.strip(), field))

            for term, field in terms:
                scanned += 1
                if imported >= max_terms:
                    break
                was_new = not any(normalize_term(item["termino_es"]) == normalize_term(term) for item in read_entries())
                upsert_term(
                    term,
                    source={
                        "fuente": "INE CKAN",
                        "dataset": dataset_slug,
                        "recurso_id": resource.get("id"),
                        "campo": field,
                    },
                )
                if was_new:
                    imported += 1

        return {
            "dataset": dataset_slug,
            "recursos_consultados": min(len(resources), max_resources),
            "terminos_nuevos": imported,
            "valores_revisados": scanned,
            "estado_traducciones": "pendientes de traducción y validación comunitaria",
            "errores_recursos": errors,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"error al importar datos del INE: {exc}")
