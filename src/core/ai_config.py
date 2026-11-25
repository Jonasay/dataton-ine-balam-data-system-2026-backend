from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

load_dotenv()

_RATE_LIMIT_PATTERN = re.compile(r"^\d+/(second|minute|hour|day)$")


class AISearchSettings(BaseModel):
    """Configuracion validada del modulo de busqueda estadistica con IA."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gemini_api_key: Optional[SecretStr] = Field(default=None)
    gemini_model: str = Field(default="gemini-2.5-flash", min_length=3, max_length=100)
    cache_ttl_seconds: int = Field(default=300, ge=1, le=86400)
    cache_maxsize: int = Field(default=256, ge=1, le=10000)
    rate_limit: str = Field(default="15/minute")
    max_rows_per_query: int = Field(default=25, ge=1, le=100)

    @field_validator("rate_limit")
    @classmethod
    def validate_rate_limit(cls, value: str) -> str:
        cleaned = value.strip()
        if not _RATE_LIMIT_PATTERN.match(cleaned):
            raise ValueError("Formato invalido para limite de tasa (ej. 15/minute).")
        return cleaned


def _env_or_default(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip()


def _env_int_or_default(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw.strip())


@lru_cache(maxsize=1)
def get_ai_search_settings() -> AISearchSettings:
    """Construir configuracion inmutable del modulo IA desde variables de entorno."""
    raw_key = os.getenv("GEMINI_API_KEY")
    secret_key = SecretStr(raw_key.strip()) if raw_key and raw_key.strip() else None

    return AISearchSettings(
        gemini_api_key=secret_key,
        gemini_model=_env_or_default("GEMINI_MODEL", "gemini-2.5-flash"),
        cache_ttl_seconds=_env_int_or_default("AI_SEARCH_CACHE_TTL_SECONDS", 300),
        cache_maxsize=_env_int_or_default("AI_SEARCH_CACHE_MAXSIZE", 256),
        rate_limit=_env_or_default("AI_SEARCH_RATE_LIMIT", "15/minute"),
    )
