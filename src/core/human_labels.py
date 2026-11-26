from __future__ import annotations

import re
from typing import Any, Dict

# Conjuntos de columnas de conteo entero (sin decimales en tablas, textos ni graficas)
INTEGER_METRIC_COLUMNS: frozenset[str] = frozenset(
    {
        "ranking",
        "posicion",
        "anio",
        "mes",
        "depto_codigo",
        "region_id",
        "cluster_id",
        "poblacion_total",
        "poblacion_2024",
        "poblacion_2030",
        "crecimiento_absoluto_2024_2030",
        "hombres",
        "mujeres",
        "pob_menor_15",
        "pob_15_64",
        "pob_65_mas",
        "defunciones_total",
        "nacimientos_total",
        "crecimiento_natural_absoluto",
        "necropsias_total",
        "victimas_viales_total",
        "fallecidos_viales_total",
        "lesionados_viales_total",
        "retornados_total",
        "retornados_hombres",
        "retornados_mujeres",
        "retornados_menores",
        "matriculados_superior_total",
        "mujeres_matriculadas_superior",
        "n_observaciones",
        "cantidad_registros",
    }
)

# Diccionario unico centralizado de etiquetas legibles en espanol (cero snake_case)
HUMAN_READABLE_LABELS: Dict[str, str] = {
    # Dimensiones territoriales, temporales y categoricas
    "ranking": "Posición",
    "posicion": "Posición",
    "anio": "Año",
    "a_o": "Año",
    "año": "Año",
    "mes": "Mes",
    "mes_nombre": "Nombre del mes",
    "depto_codigo": "Código departamento",
    "codigo_departamento": "Código departamento",
    "depto_nombre": "Departamento",
    "departamento": "Departamento",
    "depto": "Departamento",
    "departamento_f": "Departamento",
    "depto_mupio": "Municipio",
    "mupio": "Municipio",
    "depto_iso": "Código ISO",
    "region_id": "Código región",
    "codigo_region": "Código región",
    "region_nombre": "Región",
    "region": "Región",
    "mupio_codigo_str": "Código municipio",
    "codigo_municipio": "Código municipio",
    "dominio": "Área geográfica",
    "area": "Área geográfica",
    "área": "Área geográfica",
    "tipo_canasta": "Tipo de canasta",
    "canasta": "Tipo de canasta",
    "division_gasto": "División de gasto",
    "cluster_id": "Grupo territorial",
    "cluster_nombre": "Perfil territorial",
    "nivel_vulnerabilidad": "Nivel de vulnerabilidad",
    "nivel_edu": "Nivel educativo",
    "nivel": "Nivel educativo",
    "facultad": "Facultad",
    "carrera": "Carrera",
    "sector": "Sector",
    "sexo": "Sexo",
    "edad": "Edad",
    "semestre": "Semestre",
    "plan_est": "Plan de estudios",
    "pueblo_pert": "Pueblo de pertenencia",
    "pueblo_per": "Pueblo de pertenencia",
    "pais_origen": "País de origen",
    "camp_c11": "Campo educativo",
    "grup_c11": "Grupo educativo",
    "grupos_quinq": "Grupo quinquenal",
    "jornada_est": "Jornada de estudio",
    "resultado_f": "Resultado final",
    "modalidad": "Modalidad",
    # Demografia y estadisticas vitales
    "poblacion_total": "Población total",
    "poblacion_2024": "Población 2024",
    "poblacion_2030": "Población proyectada 2030",
    "crecimiento_absoluto_2024_2030": "Crecimiento poblacional (2024–2030)",
    "crecimiento_porcentual_total": "Crecimiento porcentual (%)",
    "tasa_anual_crecimiento_geometrico_pct": "Tasa de crecimiento anual (%)",
    "hombres": "Población de hombres",
    "poblacion_hombres": "Población de hombres",
    "mujeres": "Población de mujeres",
    "poblacion_mujeres": "Población de mujeres",
    "pob_menor_15": "Población menor de 15 años",
    "poblacion_menor_15": "Población menor de 15 años",
    "pob_15_64": "Población de 15 a 64 años",
    "pob_65_mas": "Población de 65 años o más",
    "defunciones_total": "Defunciones registradas",
    "nacimientos_total": "Nacimientos registrados",
    "tasa_mortalidad_por_1000": "Tasa de mortalidad (x1,000 hab.)",
    "tasa_natalidad_por_1000": "Tasa de natalidad (x1,000 hab.)",
    "crecimiento_natural_absoluto": "Crecimiento vegetativo",
    "tasa_crecimiento_natural_por_1000": "Tasa de crecimiento natural (x1,000 hab.)",
    "indice_masculinidad": "Índice de masculinidad",
    "razon_dependencia_demografica": "Razón de dependencia (%)",
    "razon_dependencia_pct": "Razón de dependencia (%)",
    "pct_poblacion_menor_15": "Población menor de 15 (%)",
    "pct_poblacion_15_64": "Población de 15 a 64 (%)",
    "pct_poblacion_65_mas": "Población de 65 o más (%)",
    # Seguridad forense y siniestralidad vial
    "necropsias_total": "Necropsias registradas",
    "tasa_necropsias_por_100k": "Tasa de necropsias (x100k hab.)",
    "victimas_viales_total": "Víctimas en accidentes viales",
    "fallecidos_viales_total": "Fallecidos en accidentes viales",
    "lesionados_viales_total": "Lesionados en accidentes viales",
    "tasa_victimas_viales_por_100k": "Tasa de víctimas viales (x100k hab.)",
    "tasa_mortalidad_vial_por_100k": "Tasa de mortalidad vial (x100k hab.)",
    # Migracion de retorno
    "retornados_total": "Personas migrantes retornadas",
    "retornados_hombres": "Hombres retornados",
    "retornados_mujeres": "Mujeres retornadas",
    "retornados_menores": "Menores retornados",
    "tasa_retorno_migratorio_por_10k": "Tasa de retorno migratorio (x10k hab.)",
    "pct_retornados_menores": "Menores retornados (%)",
    "pct_retornadas_mujeres": "Mujeres retornadas (%)",
    # Educacion superior
    "matriculados_superior_total": "Matrícula en educación superior",
    "mujeres_matriculadas_superior": "Mujeres en educación superior",
    "tasa_matricula_superior_por_10k": "Tasa de matrícula superior (x10k hab.)",
    "pct_mujeres_superior": "Mujeres en educación superior (%)",
    "porcentaje_mujeres_educacion_superior": "Mujeres en educación superior (%)",
    # Economia, canasta basica e inflacion
    "indice_ipc": "Índice de precios (IPC)",
    "indice_ipc_regional": "Índice IPC regional",
    "indice_ipc_nacional": "Índice IPC nacional",
    "inflacion_regional_interanual": "Inflación interanual (%)",
    "inflacion_interanual_pct": "Inflación interanual (%)",
    "variacion_intermensual_pct": "Variación mensual (%)",
    "variacion_interanual_pct": "Variación interanual (%)",
    "poder_adquisitivo_quetzal": "Poder adquisitivo del quetzal",
    "perdida_poder_adquisitivo": "Pérdida de poder adquisitivo (%)",
    "perdida_poder_adquisitivo_quetzal": "Pérdida de poder adquisitivo (%)",
    "costo_diario_percapita": "Costo diario per cápita (GTQ)",
    "costo_mensual_percapita": "Costo mensual per cápita (GTQ)",
    "costo_actual_percapita": "Costo mensual actual (GTQ)",
    "tendencia_mensual_gtq": "Variación mensual estimada (GTQ)",
    "crecimiento_mensual_pct": "Crecimiento mensual estimado (%)",
    "proyeccion_tasa_anual_pct": "Proyección anual (%)",
    "proyeccion_3_meses_gtq": "Proyección a 3 meses (GTQ)",
    "proyeccion_6_meses_gtq": "Proyección a 6 meses (GTQ)",
    "proyeccion_12_meses_gtq": "Proyección a 12 meses (GTQ)",
    "brecha_urbano_rural_cba_gtq": "Brecha urbano-rural CBA (GTQ)",
    "brecha_urbano_rural_cba_pct": "Brecha urbano-rural CBA (%)",
    # Vulnerabilidad y ciencia de datos
    "indice_vulnerabilidad_ivst": "Índice de vulnerabilidad (IVST)",
    "variable": "Indicador",
    "n_observaciones": "Observaciones",
    "media": "Promedio",
    "desviacion_estandar": "Desviación estándar",
    "mediana": "Mediana",
    "minimo": "Valor mínimo",
    "maximo": "Valor máximo",
    "coeficiente_variacion_pct": "Coeficiente de variación (%)",
    "variable_1": "Indicador A",
    "variable_2": "Indicador B",
    "pearson_r": "Correlación de Pearson (r)",
    "pearson_pvalue": "Significancia (valor p)",
    "spearman_rho": "Correlación de Spearman (ρ)",
    "fuerza_asociacion": "Fuerza de asociación",
    # Conteos dinamicos
    "cantidad_registros": "Cantidad de registros",
    "porcentaje_pct": "Participación (%)",
}


def humanize_label(raw_key: str) -> str:
    """Traducir cualquier identificador tecnico a etiqueta legible en espanol sin guiones bajos."""
    cleaned = str(raw_key or "").strip()
    if not cleaned:
        return "Valor"
    if cleaned in HUMAN_READABLE_LABELS:
        return HUMAN_READABLE_LABELS[cleaned]
    lower = cleaned.lower()
    if lower in HUMAN_READABLE_LABELS:
        return HUMAN_READABLE_LABELS[lower]
    normalized = re.sub(r"[_\s]+", " ", cleaned).strip()
    if not normalized:
        return "Valor"
    return normalized[0].upper() + normalized[1:]


def format_metric_for_summary(col_key: str, value: Any) -> str:
    """Formatear un valor estadistico para texto narrativo (enteros sin decimales, tasas con 2 decimales)."""
    if value is None:
        return "N/D"
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, int) or col_key in INTEGER_METRIC_COLUMNS:
        try:
            return f"{int(round(float(value))):,}"
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, float):
        suffix = "%" if ("pct" in col_key or "(%)" in humanize_label(col_key)) else ""
        return f"{value:,.2f}{suffix}"
    return str(value)
