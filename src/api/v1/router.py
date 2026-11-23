from __future__ import annotations

from fastapi import APIRouter
from src.api.v1.endpoints import ine_router, process_router

# enrutador version 1 con prefijo para modularizar servicios
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(ine_router.router)
api_router.include_router(process_router.router)