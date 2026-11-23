# Datatón INE - Balam Data System 2026 (Backend)

API backend desarrollada con **FastAPI** y **Python** para el sistema de análisis, procesamiento y consulta de datos.

---

## 📋 Requisitos Previos

- **Python**: Versión **3.12**.
- **Git**: Para el control de versiones.
- **pip o uv**: Gestor de paquetes de Python (incluido por defecto con Python).

---

## 🚀 Guía de Instalación y Ejecución (Windows, macOS y Linux)

Sigue estos pasos para levantar el entorno de desarrollo en cualquier sistema operativo.

### 1. Clonar el Repositorio

```bash
git clone <URL_DEL_REPOSITORIO>
cd dataton-ine-balam-data-system-2026-backend
```

---

### 2. Crear el Entorno Virtual (`.venv`)

Asegúrate de estar en la raíz del proyecto.

- **Linux / macOS**:
  ```bash
  python3 -m venv .venv
  ```

- **Windows (PowerShell o CMD)**:
  ```powershell
  python -m venv .venv
  ```

---

### 3. Activar el Entorno Virtual

El comando de activación varía según el sistema operativo y la terminal:

#### 🐧 Linux / 🍎 macOS (Bash / Zsh):
```bash
source .venv/bin/activate
```

#### 🪟 Windows (PowerShell):
```powershell
.\.venv\Scripts\Activate.ps1
```
> **Nota para Windows (PowerShell):** Si aparece un error de políticas de ejecución (`ExecutionPolicy`), habilita la ejecución en la sesión actual con:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
> ```

#### 🪟 Windows (CMD / Símbolo del Sistema):
```cmd
.\.venv\Scripts\activate.bat
```

> **Verificación:** Al estar activo verás `(.venv)` al principio de tu terminal.

---

### 4. Actualizar pip e Instalar Dependencias

Con el entorno virtual activado:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

*(Si necesitas instalar el conjunto estándar de herramientas de FastAPI: `pip install "fastapi[standard]"`)*

---

### 5. Configurar Variables de Entorno

El proyecto incluye un archivo de ejemplo `.env.example`. Crea una copia llamada `.env`:

- **Linux / macOS**:
  ```bash
  cp .env.example .env
  ```

- **Windows (PowerShell)**:
  ```powershell
  Copy-Item .env.example .env
  ```

- **Windows (CMD)**:
  ```cmd
  copy .env.example .env
  ```

Edita `.env` y define las variables requeridas (por ejemplo, el puerto):
```env
PORT=8080
```

---

### 6. Levantar el Servidor de Desarrollo

Puedes iniciar el servidor mediante el CLI de FastAPI o con Uvicorn:

#### Opción A: Con FastAPI CLI (Recomendado)
```bash
fastapi dev main.py --port 8080
```

#### Opción B: Con Uvicorn
```bash
uvicorn main:app --reload --port 8080
```
o
```bash
python -m uvicorn main:app --reload --port 8080
```

El servicio estará disponible en: **`http://localhost:8080`**

---

### 7. Documentación Interactiva de la API

Una vez levantado el servidor, FastAPI genera automáticamente la documentación interactiva:

- **Swagger UI:** [http://localhost:8080/docs](http://localhost:8080/docs)
- **ReDoc:** [http://localhost:8080/redoc](http://localhost:8080/redoc)

---

## ⚡ Alternativa Rápida con `uv` (Opcional)

Si utilizas [`uv`](https://github.com/astral-sh/uv) como gestor de paquetes de alto rendimiento:

```bash
# Crear entorno virtual con Python 3.12
uv venv .venv --python 3.12

# Activar (.venv)
# En Linux / macOS:
source .venv/bin/activate
# En Windows:
.\.venv\Scripts\activate

# Instalar dependencias
uv pip install -r requirements.txt

# Levantar servidor
fastapi dev main.py --port 8080
```

---

## 🛠️ Comandos de Utilidad

- **Desactivar el entorno virtual:**
  ```bash
  deactivate
  ```
- **Congelar / Actualizar archivo de dependencias:**
  ```bash
  pip freeze > requirements.txt
  ```
