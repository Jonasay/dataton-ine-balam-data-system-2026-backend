from __future__ import annotations

import re
import threading
from typing import Optional

from cachetools import TTLCache

from src.schemas.ai_search import AISearchResponse

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_cache_key(query: str) -> str:
    """Normalizar texto de consulta (minusculas y espacios limpios) para clave de cache."""
    return _WHITESPACE_RE.sub(" ", query.strip().lower())


class AIQueryCache:
    """Cache en memoria con expiracion TTL segura para concurrencia."""

    def __init__(self, maxsize: int = 256, ttl_seconds: int = 300) -> None:
        self._cache: TTLCache[str, AISearchResponse] = TTLCache(maxsize=maxsize, ttl=ttl_seconds)
        self._lock = threading.RLock()

    def get(self, raw_query: str) -> Optional[AISearchResponse]:
        key = normalize_cache_key(raw_query)
        with self._lock:
            cached = self._cache.get(key)
            return cached.model_copy(deep=True) if cached is not None else None

    def set(self, raw_query: str, response: AISearchResponse) -> None:
        key = normalize_cache_key(raw_query)
        with self._lock:
            self._cache[key] = response.model_copy(deep=True)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
