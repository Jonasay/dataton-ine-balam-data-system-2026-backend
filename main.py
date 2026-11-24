from __future__ import annotations

from fastapi import FastAPI
from scalar_fastapi import get_scalar_api_reference

from src.api.v1.endpoints.ine_router import router as ine_direct_router
from src.api.v1.endpoints.process_router import router as process_direct_router
from src.api.v1.router import api_router

app = FastAPI(
    title="Balam Data Systems",
    description="Documentacion de la api para el dataton ine 2026 - balam data systems (bds)",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)

# inclusion de enrutadores versionados y directos para maxima compatibilidad
app.include_router(api_router)
app.include_router(ine_direct_router, include_in_schema=False)
app.include_router(process_direct_router, include_in_schema=False)


# interfaz grafica scalar para explorar la documentacion interactiva
@app.get("/docs", include_in_schema=False)
async def scalar_docs():
    """Renderizar interfaz de documentacion con scalar."""
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )
