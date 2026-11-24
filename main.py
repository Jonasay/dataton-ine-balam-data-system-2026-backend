from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from scalar_fastapi import get_scalar_api_reference

from src.api.v1.endpoints.ine_router import router as ine_direct_router
from src.api.v1.endpoints.process_router import router as process_direct_router
from src.api.v1.endpoints.indicators_router import router as indicators_direct_router
from src.api.v1.endpoints.analytics_router import router as analytics_direct_router
from src.api.v1.endpoints.visualizations_router import router as visualizations_direct_router
from src.api.v1.router import api_router

app = FastAPI(
    title="Balam Data Systems - Plataforma Socioeconómica de Guatemala",
    description="Servicios API REST oficiales para análisis socioeconómico, pobreza, migración y dinamica territorial (INE 2026)",
    version="1.1.0",
    docs_url=None,
    redoc_url=None,
)

# configuracion cors para integracion directa con aplicaciones frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# inclusion de enrutadores versionados y directos para maxima compatibilidad
app.include_router(api_router)
app.include_router(ine_direct_router, include_in_schema=False)
app.include_router(process_direct_router, include_in_schema=False)
app.include_router(indicators_direct_router, include_in_schema=False)
app.include_router(analytics_direct_router, include_in_schema=False)
app.include_router(visualizations_direct_router, include_in_schema=False)


# redireccion raiz al portal interactivo del stack visual completo
@app.get("/", include_in_schema=False)
async def root_portal():
    return RedirectResponse(url="/api/v1/visualizaciones/stack-completo")


# interfaz grafica scalar para explorar la documentacion interactiva
@app.get("/docs", include_in_schema=False)
async def scalar_docs():
    """Renderizar interfaz de documentacion con scalar."""
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )


# endpoints de verificacion de estado y salud del servicio
@app.get("/", tags=["Salud y Estado"])
def home():
    """Verificar que la api principal esta activa."""
    return {"message": "API de Balam Data Systems"}


@app.get("/health", tags=["Salud y Estado"])
def health_check():
    """Verificar estado de salud del contenedor y servicio."""
    return {
        "status": "ok",
        "service": app.title,
        "version": app.version,
    }
