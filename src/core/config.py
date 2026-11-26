from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# directorio raiz del repositorio backend para resolver rutas relativas y .env
BACKEND_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# cargar variables de entorno desde el archivo .env del backend
load_dotenv(BACKEND_ROOT / ".env")

def _env_str(name: str, default: str) -> str:
    """Leer variable de entorno de texto con respaldo seguro si falta o esta vacia."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    """Leer variable de entorno entera con respaldo seguro si falta o es invalida."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _resolve_project_path(raw_value: str) -> Path:
    """Resolver ruta relativa respecto a BACKEND_ROOT sin alterar rutas absolutas."""
    candidate = Path(raw_value)
    return candidate if candidate.is_absolute() else (BACKEND_ROOT / candidate)


# parametros del servidor y ckan ine tomados del entorno con valores por defecto seguros
PORT: int = _env_int("PORT", 8000)
BASE_URL_INE: str = _env_str("BASE_PATH_INE", "https://datos.ine.gob.gt/api/3/action").rstrip("/")
DEFAULT_REQUEST_TIMEOUT: int = _env_int("INE_REQUEST_TIMEOUT", 60)
DEFAULT_DOWNLOAD_TIMEOUT: int = _env_int("INE_DOWNLOAD_TIMEOUT", 300)

# directorios de almacenamiento local y cabeceras tomadas del entorno
RAW_DATA_DIR: Path = _resolve_project_path(_env_str("RAW_DATA_PATH", "data/raw"))
PROCESSED_DATA_DIR: Path = _resolve_project_path(_env_str("PROCESSED_DATA_PATH", "data/processed"))
DEFAULT_USER_AGENT: str = _env_str("USER_AGENT", "datathon-ine-2026 (equipo: balam-data-systems)")
DEFAULT_HEADERS: dict[str, str] = {"User-Agent": DEFAULT_USER_AGENT}

# clave de api para integraciones opcionales con gemini tomada solo desde entorno
GEMINI_API_KEY: str = _env_str("GEMINI_API_KEY", "")