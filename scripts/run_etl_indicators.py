from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

# asegurar ruta raiz del proyecto en sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.core.config import DEFAULT_HEADERS, PROCESSED_DATA_DIR, RAW_DATA_DIR
from src.process.run_etl import run_full_etl
from src.analysis.indicators import (
    compute_consolidated_department_dataset,
    compute_consolidated_municipal_dataset,
)

# catalogo de recursos crudos requeridos para el pipeline
REQUIRED_RESOURCES = [
    {
        "dataset": "proyecciones-de-poblacion-2015-2030",
        "name": "proyecciones_poblacion_2015_2030",
        "url": "https://datos.ine.gob.gt/dataset/23bbe8f8-ec9b-49c9-bcca-de78bec4efc0/resource/56b97bc0-5624-408d-a136-3931dd05610a/download/estimaciones-y-proyecciones-de-la-poblacion-total-por-municipio-segun-sexo-y-edad.-2015-2030.xlsx",
        "local_path": "data/raw/proyecciones-de-poblacion-2015-2030/estimaciones-y-proyecciones-de-la-poblacion-total-por-municipio-segun-sexo-y-edad.-2015-2030.xlsx",
    },
    {
        "dataset": "costos-de-la-cba-urbana-y-rural",
        "name": "cba_rural",
        "url": "https://datos.ine.gob.gt/dataset/0317e7b9-9563-4a9c-800f-c74473103063/resource/69abf503-56da-4de5-9017-875009394843/download/costo-cba-percapita_r.xlsx",
        "local_path": "data/raw/costos-de-la-cba-urbana-y-rural/costo-cba-percapita_r.xlsx",
    },
    {
        "dataset": "costos-de-la-cba-urbana-y-rural",
        "name": "cba_urbana",
        "url": "https://datos.ine.gob.gt/dataset/0317e7b9-9563-4a9c-800f-c74473103063/resource/6721d034-7af0-4622-ae34-be10f0f2ac89/download/costo-cba-percapita_u.xlsx",
        "local_path": "data/raw/costos-de-la-cba-urbana-y-rural/costo-cba-percapita_u.xlsx",
    },
    {
        "dataset": "costos-de-la-cba-urbana-y-rural",
        "name": "ca_rural",
        "url": "https://datos.ine.gob.gt/dataset/0317e7b9-9563-4a9c-800f-c74473103063/resource/b5636c04-a157-4b82-9391-2921399b0ef1/download/costo-campliada-rural-2-1.xlsx",
        "local_path": "data/raw/costos-de-la-cba-urbana-y-rural/costo-campliada-rural-2-1.xlsx",
    },
    {
        "dataset": "costos-de-la-cba-urbana-y-rural",
        "name": "ca_urbana",
        "url": "https://datos.ine.gob.gt/dataset/0317e7b9-9563-4a9c-800f-c74473103063/resource/1cdb0eab-2b96-4fed-8954-85f28f93f0ad/download/costo-campliada-urbana-2.xlsx",
        "local_path": "data/raw/costos-de-la-cba-urbana-y-rural/costo-campliada-urbana-2.xlsx",
    },
    {
        "dataset": "indicadores-ipc-base-diciembre-2023-100-0",
        "name": "ipc_divisiones_gasto",
        "url": "https://datos.ine.gob.gt/dataset/5749eeeb-7fe0-4d6f-97a4-ca9a7de0dbc2/resource/629d992d-99a6-4e1d-b4d1-cd4bdec02f94/download/ipc_divga_b23_es24.xlsx",
        "local_path": "data/raw/indicadores-ipc-base-diciembre-2023-100-0/ipc_divga_b23_es24.xlsx",
    },
    {
        "dataset": "indicadores-ipc-base-diciembre-2023-100-0",
        "name": "ipc_poder_adquisitivo",
        "url": "https://datos.ine.gob.gt/dataset/5749eeeb-7fe0-4d6f-97a4-ca9a7de0dbc2/resource/7755dec3-9165-4c48-8a55-5e04ee49c2a5/download/ipc_perypod_b23_es24.xlsx",
        "local_path": "data/raw/indicadores-ipc-base-diciembre-2023-100-0/ipc_perypod_b23_es24.xlsx",
    },
    {
        "dataset": "indicadores-ipc-base-diciembre-2023-100-0",
        "name": "ipc_regiones",
        "url": "https://datos.ine.gob.gt/dataset/5749eeeb-7fe0-4d6f-97a4-ca9a7de0dbc2/resource/4f96e464-6961-4d74-910c-77a699ac2a9d/download/ipc_reg_b23_es24.xlsx",
        "local_path": "data/raw/indicadores-ipc-base-diciembre-2023-100-0/ipc_reg_b23_es24.xlsx",
    },
    {
        "dataset": "indicadores-ipc-base-diciembre-2023-100-0",
        "name": "ipc_variacion_divisiones",
        "url": "https://datos.ine.gob.gt/dataset/5749eeeb-7fe0-4d6f-97a4-ca9a7de0dbc2/resource/626afe67-eac4-4c11-a075-3df792b4633b/download/ipc_varintdivga_b23_es24.xlsx",
        "local_path": "data/raw/indicadores-ipc-base-diciembre-2023-100-0/ipc_varintdivga_b23_es24.xlsx",
    },
    {
        "dataset": "indicadores-ipc-base-diciembre-2023-100-0",
        "name": "ipc_variacion_regiones",
        "url": "https://datos.ine.gob.gt/dataset/5749eeeb-7fe0-4d6f-97a4-ca9a7de0dbc2/resource/58bb5909-794c-4283-8afb-9294424be207/download/ipc_varinreg_b23_es24.xlsx",
        "local_path": "data/raw/indicadores-ipc-base-diciembre-2023-100-0/ipc_varinreg_b23_es24.xlsx",
    },
    {
        "dataset": "estadisticas-vitales-defunciones",
        "name": "defunciones_2024",
        "url": "https://datos.ine.gob.gt/dataset/14f547c3-ad37-4ea1-9e74-16a3ed50ff54/resource/db7d7ce4-a450-466b-9bd9-8150eb55c34b/download/bd-defunciones-2024-da.xlsx",
        "local_path": "data/raw/estadisticas-vitales-defunciones/bd-defunciones-2024-da.xlsx",
    },
    {
        "dataset": "estadisticas-vitales-nacimientos",
        "name": "nacimientos_2025",
        "url": "https://datos.ine.gob.gt/dataset/96888fc0-5ced-4a58-bfd0-2a6a292e3208/resource/b6847c70-a0b9-4cfd-a405-4ea4360905d7/download/nacimientos_2025.xlsx",
        "local_path": "data/raw/estadisticas-vitales-nacimientos/nacimientos_2025.xlsx",
    },
    {
        "dataset": "hechos-delictivos-servicio-medico-necropsias-inacif",
        "name": "necropsias_inacif_2024",
        "url": "https://datos.ine.gob.gt/dataset/cc975da9-d43f-46f6-ad5a-4e0cb3514300/resource/dd00d3ac-96d1-43fa-8611-8cfa14926509/download/base-de-datos-necropsias-inacif-2024.xlsx",
        "local_path": "data/raw/hechos-delictivos-servicio-medico-necropsias-inacif/base-de-datos-necropsias-inacif-2024.xlsx",
    },
    {
        "dataset": "educacion-superior-matriculados",
        "name": "matriculados_superior_2025",
        "url": "https://datos.ine.gob.gt/dataset/8bec075d-31b3-465c-a3a9-597b08618401/resource/18027628-af8a-469c-b293-243f7803ba0b/download/matriculados_educacion_superior-2025.xlsx",
        "local_path": "data/raw/educacion-superior-matriculados/matriculados_educacion_superior-2025.xlsx",
    },
    {
        "dataset": "accidentes-de-transito-fallecidos-y-lesionados",
        "name": "accidentes_fallecidos_lesionados_2024",
        "url": "https://datos.ine.gob.gt/dataset/b80e7836-a158-4830-9177-bca5a3b6cf0d/resource/d4505add-cbc1-4a1a-a35b-dcd73694d0fe/download/base-de-datos-fallecidos-y-lesionados-pnc-2024.xlsx",
        "local_path": "data/raw/accidentes-de-transito-fallecidos-y-lesionados/base-de-datos-fallecidos-y-lesionados-pnc-2024.xlsx",
    },
    {
        "dataset": "retornados-ano-2024vv",
        "name": "retornados_2024",
        "url": "https://datos.ine.gob.gt/dataset/833bf4fb-347b-4d71-a30d-2fafa1e575f6/resource/e861905d-09fe-4a1f-a3d8-bd36bf2ddc26/download/bd_retornados_ano_2024.xlsx",
        "local_path": "data/raw/retornados-ano-2024vv/bd_retornados_ano_2024.xlsx",
    },
    {
        "dataset": "retornados",
        "name": "retornados_usa_aereo_2023",
        "url": "https://datos.ine.gob.gt/dataset/0c3ea9a7-50bd-4cc7-b7fc-44989897fb5b/resource/f8467232-5879-4936-b8a2-afaa60ff4d64/download/retornados_usa_aereo.csv",
        "local_path": "data/raw/retornados/retornados_usa_aereo.csv",
    },
]


def download_file_with_retry(url: str, target_path: Path, max_retries: int = 4) -> bool:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(target_path.suffix + ".part")
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"  descargando {target_path.name} (intento {attempt}/{max_retries})...")
            response = requests.get(url, headers=DEFAULT_HEADERS, stream=True, timeout=120)
            response.raise_for_status()
            
            hasher = hashlib.sha256()
            with open(temp_path, "wb") as file_handle:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        file_handle.write(chunk)
                        hasher.update(chunk)
                        
            temp_path.replace(target_path)
            size_mb = target_path.stat().st_size / (1024 * 1024)
            print(f"  ✓ guardado exitosamente: {target_path.name} ({size_mb:.2f} mb)")
            return True
        except Exception as exc:
            print(f"  aviso en intento {attempt}: {exc}")
            if temp_path.exists():
                temp_path.unlink()
            if attempt < max_retries:
                time.sleep(2 * attempt)
    return False


def ensure_raw_datasets():
    # verificar y crear directorios base si no existen
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    trash_raw = Path.home() / ".local" / "share" / "Trash" / "files" / "data" / "raw"
    missing_items = []
    
    for item in REQUIRED_RESOURCES:
        target_path = root_dir / item["local_path"]
        if not target_path.exists() or target_path.stat().st_size == 0:
            # si el archivo existe en papelera recuperarlo inmediatamente
            trash_candidate = trash_raw / Path(item["local_path"]).relative_to("data/raw")
            if trash_candidate.exists() and trash_candidate.stat().st_size > 0:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(trash_candidate, target_path)
                print(f"  recuperado de respaldo local: {target_path.name}")
            else:
                missing_items.append((item, target_path))
                
    if missing_items:
        print(f"\nse detectaron {len(missing_items)} archivos faltantes en data/raw. iniciando descarga automatica desde ine...")
        for item, target_path in missing_items:
            success = download_file_with_retry(item["url"], target_path)
            if not success:
                print(f"advertencia: no se pudo descargar {item['name']}")

    # asegurar capa geografica departamental para mapas 2d y relieve 3d
    from src.core.geo_master import ensure_guatemala_geojson
    geo_file = ensure_guatemala_geojson(root_dir / "data" / "raw" / "geo" / "departamentos_gt.geojson")
    print(f"  ✓ capa geografica disponible en: {geo_file}")


def run_pipeline(year: int = 2024):
    start_time = time.time()
    
    # 1. asegurar existencia de datos crudos
    print("=" * 70)
    print("verificando conjunto de datos crudos en data/raw...")
    print("=" * 70)
    ensure_raw_datasets()

    # 2. ejecutar proceso etl hacia parquet
    print("\n" + "=" * 70)
    print("iniciando procesamiento etl hacia apache parquet")
    print("=" * 70)
    run_full_etl()

    # 3. calcular y consolidar matriz de indicadores departamentales y municipales
    print("\n" + "=" * 70)
    print(f"calculando y consolidando indicadores para el anio {year}")
    print("=" * 70)
    indicators_df = compute_consolidated_department_dataset(year=year)
    mup_indicators_df = compute_consolidated_municipal_dataset(year=year)

    # 4. mostrar resumen de indicadores principales
    display_cols = [
        "depto_codigo", "depto_nombre", "poblacion_total",
        "tasa_natalidad_por_1000", "tasa_mortalidad_por_1000",
        "tasa_necropsias_por_100k", "tasa_victimas_viales_por_100k",
        "tasa_retorno_migratorio_por_10k", "tasa_matricula_superior_por_10k",
        "inflacion_regional_interanual",
    ]
    
    print("\n" + "=" * 70)
    print("resumen de indicadores por departamento:")
    print("=" * 70)
    print(indicators_df.select(display_cols).sort("tasa_retorno_migratorio_por_10k", descending=True))

    mup_cols = [
        "mupio_codigo_str", "depto_nombre", "poblacion_total",
        "tasa_natalidad_por_1000", "tasa_mortalidad_por_1000",
        "tasa_necropsias_por_100k", "tasa_victimas_viales_por_100k",
        "tasa_matricula_superior_por_10k",
    ]
    print("\n" + "=" * 70)
    print("resumen de indicadores por municipio (muestra de 5 con mayor poblacion):")
    print("=" * 70)
    print(mup_indicators_df.sort("poblacion_total", descending=True).select(mup_cols).head(5))

    elapsed = time.time() - start_time
    print("\n" + "=" * 70)
    print(f"pipeline completo finalizado exitosamente en {elapsed:.2f} segundos")
    print("=" * 70)


if __name__ == "__main__":
    target_year = 2024
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        target_year = int(sys.argv[1])
    run_pipeline(year=target_year)
