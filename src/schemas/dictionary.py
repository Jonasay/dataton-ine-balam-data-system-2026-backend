from __future__ import annotations

from pydantic import BaseModel, Field


class DictionaryTermRequest(BaseModel):
    termino_es: str = Field(..., min_length=1, max_length=200)
    definicion_es: str = Field(default="", max_length=2000)


class DictionaryTranslationRequest(BaseModel):
    traduccion: str = Field(..., min_length=1, max_length=500)
    validado: bool = False
