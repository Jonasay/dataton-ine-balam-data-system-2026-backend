from fastapi import FastAPI
from scalar_fastapi import get_scalar_api_reference

app = FastAPI(
    title="Balam Data Systems",
    description="Documentación de la API para el Dataton INE 2026 - Balam Data Systems (BDS)",
    version="1.0.0",
    docs_url=None,
    redoc_url=None
)

# configuración para Scalar UI
@app.get("/docs", include_in_schema=False)
async def scalar_docs():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )

# Endpoint para verificar que la API funciona
@app.get("/")
def home():
    return {"message": "API de Balam Data Systems"}
