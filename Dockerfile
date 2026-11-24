# imagen base python 3.12 sobre debian bookworm
FROM python:3.12-slim-bookworm

# configuracion de entorno para python y pip
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# instalar dependencias del sistema y blender headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    blender \
    ca-certificates \
    curl \
    libgl1 \
    libxi6 \
    libxkbcommon0 \
    libxrender1 \
    libxxf86vm1 \
    libxfixes3 \
    libsm6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# instalar dependencias del proyecto
COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# copiar codigo fuente y preparar directorio de datos
COPY main.py .
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY test/ ./test/
RUN mkdir -p /app/data/raw /app/data/processed

# ejecutar pipeline etl e indicadores, ciencia de datos y levantar servidor con el puerto de .env
CMD ["sh", "-c", "python scripts/run_etl_indicators.py && python scripts/run_data_science.py && uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
