# imagen base python 3.12 sobre debian bookworm
FROM python:3.12-slim-bookworm

# configuracion de entorno para python y pip
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
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

# copiar codigo fuente
COPY main.py .
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY test/ ./test/
COPY data/ ./data/

# iniciar servidor usando el puerto configurado en .env
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
