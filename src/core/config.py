"""Configuracion centralizada de la aplicacion backend balam data systems."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# cargar variables de entorno desde el archivo .env
load_dotenv()

# parametros del servidor y ckan ine tomados exclusivamente del entorno sin valores quemados
PORT: int = int(os.getenv("PORT"))
BASE_URL_INE: str = os.getenv("BASE_PATH_INE").rstrip("/")
DEFAULT_REQUEST_TIMEOUT: int = int(os.getenv("INE_REQUEST_TIMEOUT"))
DEFAULT_DOWNLOAD_TIMEOUT: int = int(os.getenv("INE_DOWNLOAD_TIMEOUT"))

# directorio de almacenamiento local y cabeceras tomadas del entorno
RAW_DATA_DIR: Path = Path(os.getenv("RAW_DATA_PATH"))
DEFAULT_USER_AGENT: str = os.getenv("USER_AGENT")
DEFAULT_HEADERS: dict[str, str] = {"User-Agent": DEFAULT_USER_AGENT}
