from __future__ import annotations
from fastapi import APIRouter
from src.api.v1.endpoints import ine_router

# enrutador version 1 con prefijo para modularizar servicios
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(ine_router.router)

# verificacion del estado de la aplicacion
@api_router.get("/", summary="Estado del servicio")
def home():
    """Verificar que el servicio se encuentra activo."""
    return {"mensaje": "API de Balam Data Systems"}