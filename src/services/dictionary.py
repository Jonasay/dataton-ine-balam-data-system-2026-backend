from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from src.core.config import PROCESSED_DATA_DIR

DICTIONARY_FILE = PROCESSED_DATA_DIR / "diccionario_idiomas_mayas.json"
SUPPORTED_LANGUAGES = {
    "es": "Español",
    "quc": "K'iche'",
    "mam": "Mam",
    "cak": "Kaqchikel",
    "qeq": "Q'eqchi'",
    "tzu": "Tz'utujil",
    "usp": "Uspanteko",
    "pop": "Popti'",
}
_TERM_RE = re.compile(r"\s+")


def normalize_term(value: str) -> str:
    return _TERM_RE.sub(" ", value.strip()).casefold()


def read_entries(path: Path = DICTIONARY_FILE) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("el archivo del diccionario debe contener una lista")
    return payload


def write_entries(entries: list[dict[str, Any]], path: Path = DICTIONARY_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix="diccionario-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def upsert_term(
    term: str,
    *,
    definition_es: str = "",
    language: str | None = None,
    translation: str | None = None,
    source: dict[str, Any] | None = None,
    path: Path = DICTIONARY_FILE,
) -> dict[str, Any]:
    clean_term = _TERM_RE.sub(" ", term.strip())
    if not clean_term:
        raise ValueError("el término no puede estar vacío")
    if language and language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"idioma no soportado: {language}")

    entries = read_entries(path)
    normalized = normalize_term(clean_term)
    entry = next((item for item in entries if normalize_term(item["termino_es"]) == normalized), None)
    if entry is None:
        entry = {
            "termino_es": clean_term,
            "definicion_es": definition_es.strip(),
            "traducciones": {},
            "fuentes": [],
            "estado": "pendiente",
        }
        entries.append(entry)
    elif definition_es.strip():
        entry["definicion_es"] = definition_es.strip()

    if language and translation and translation.strip():
        entry["traducciones"][language] = {
            "texto": translation.strip(),
            "validado": False,
        }
        entry["estado"] = "en_revision"

    if source and source not in entry["fuentes"]:
        entry["fuentes"].append(source)

    write_entries(entries, path)
    return entry


def update_translation(
    term: str,
    language: str,
    translation: str,
    *,
    validated: bool = False,
    path: Path = DICTIONARY_FILE,
) -> dict[str, Any] | None:
    if language not in SUPPORTED_LANGUAGES or language == "es":
        raise ValueError("seleccione un idioma maya soportado")
    entries = read_entries(path)
    entry = next((item for item in entries if normalize_term(item["termino_es"]) == normalize_term(term)), None)
    if entry is None:
        return None
    entry["traducciones"][language] = {"texto": translation.strip(), "validado": validated}
    entry["estado"] = "validado" if validated else "en_revision"
    write_entries(entries, path)
    return entry
