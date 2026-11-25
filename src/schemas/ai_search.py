from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]+")
_MULTISPACE_RE = re.compile(r"\s+")

# Listas blancas estrictas generadas a partir de los datasets agregados reales en data/processed/
IntentType = Literal[
    "consulta_estadistica",
    "bloqueo_privacidad",
    "fuera_de_dominio",
]

DatasetId = Literal[
    "indicadores_departamentales",
    "indicadores_municipales",
    "vulnerabilidad_departamental",
    "clusters_departamentales",
    "trayectoria_demografica",
    "proyecciones_demograficas",
    "canasta_basica_mensual",
    "proyecciones_costo_vida",
    "ipc_regiones",
    "ipc_divisiones_gasto",
    "ipc_poder_adquisitivo",
    "estadisticas_descriptivas",
    "matriz_correlaciones",
]

AllowedColumn = Literal[
    # Dimensiones territoriales y temporales
    "ranking",
    "anio",
    "mes",
    "mes_nombre",
    "depto_codigo",
    "depto_nombre",
    "region_id",
    "region_nombre",
    "mupio_codigo_str",
    "dominio",
    "tipo_canasta",
    "division_gasto",
    "cluster_id",
    "cluster_nombre",
    "nivel_vulnerabilidad",
    # Indicadores demograficos y vitales
    "poblacion_total",
    "poblacion_2024",
    "poblacion_2030",
    "crecimiento_absoluto_2024_2030",
    "crecimiento_porcentual_total",
    "tasa_anual_crecimiento_geometrico_pct",
    "hombres",
    "mujeres",
    "pob_menor_15",
    "pob_15_64",
    "pob_65_mas",
    "defunciones_total",
    "nacimientos_total",
    "tasa_mortalidad_por_1000",
    "tasa_natalidad_por_1000",
    "crecimiento_natural_absoluto",
    "tasa_crecimiento_natural_por_1000",
    "indice_masculinidad",
    "razon_dependencia_demografica",
    "pct_poblacion_menor_15",
    "pct_poblacion_15_64",
    "pct_poblacion_65_mas",
    # Seguridad y siniestralidad vial
    "necropsias_total",
    "tasa_necropsias_por_100k",
    "victimas_viales_total",
    "fallecidos_viales_total",
    "lesionados_viales_total",
    "tasa_victimas_viales_por_100k",
    "tasa_mortalidad_vial_por_100k",
    # Migracion de retorno
    "retornados_total",
    "retornados_hombres",
    "retornados_mujeres",
    "retornados_menores",
    "tasa_retorno_migratorio_por_10k",
    "pct_retornados_menores",
    "pct_retornadas_mujeres",
    # Educacion superior
    "matriculados_superior_total",
    "mujeres_matriculadas_superior",
    "tasa_matricula_superior_por_10k",
    "pct_mujeres_superior",
    # Economia, canasta basica e inflacion
    "indice_ipc",
    "indice_ipc_regional",
    "indice_ipc_nacional",
    "inflacion_regional_interanual",
    "variacion_intermensual_pct",
    "variacion_interanual_pct",
    "poder_adquisitivo_quetzal",
    "perdida_poder_adquisitivo",
    "perdida_poder_adquisitivo_quetzal",
    "costo_diario_percapita",
    "costo_mensual_percapita",
    "costo_actual_percapita",
    "tendencia_mensual_gtq",
    "crecimiento_mensual_pct",
    "proyeccion_tasa_anual_pct",
    "proyeccion_3_meses_gtq",
    "proyeccion_6_meses_gtq",
    "proyeccion_12_meses_gtq",
    "brecha_urbano_rural_cba_gtq",
    "brecha_urbano_rural_cba_pct",
    # Vulnerabilidad y ciencia de datos
    "indice_vulnerabilidad_ivst",
    "variable",
    "n_observaciones",
    "media",
    "desviacion_estandar",
    "mediana",
    "minimo",
    "maximo",
    "coeficiente_variacion_pct",
    "variable_1",
    "variable_2",
    "pearson_r",
    "pearson_pvalue",
    "spearman_rho",
    "fuerza_asociacion",
]

VisualizationKind = Literal[
    "ninguna",
    "ranking_departamental",
    "ranking_municipal",
    "mapa_3d_relieve",
    "mapa_2d_plotly",
    "mapa_2d_folium",
    "tendencia_costo_vida",
    "tendencia_ipc_regiones",
    "tendencia_ipc_divisiones",
    "tendencia_poder_adquisitivo",
    "crecimiento_demografico",
    "clusters_pca_3d",
    "trayectoria_demografica_3d",
    "trayectoria_costo_vida_3d",
    "heatmap_correlaciones",
    "radar_departamental",
]


class AISearchRequest(BaseModel):
    """Contrato publico de entrada para consultas estadisticas en lenguaje natural."""

    model_config = ConfigDict(extra="forbid")

    consulta: str = Field(
        ...,
        min_length=3,
        max_length=300,
        description="Pregunta ciudadana sobre estadisticas oficiales agregadas (3 a 300 caracteres).",
        examples=["¿Cuáles son los 5 departamentos con mayor tasa de retorno migratorio?"],
    )

    @field_validator("consulta", mode="before")
    @classmethod
    def sanitize_raw_query(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("La consulta debe ser una cadena de texto.")
        without_control = _CONTROL_CHARS_RE.sub(" ", value)
        collapsed = _MULTISPACE_RE.sub(" ", without_control).strip()
        return collapsed

    @field_validator("consulta", mode="after")
    @classmethod
    def validate_sanitized_bounds(cls, value: str) -> str:
        if len(value) < 3:
            raise ValueError("La consulta debe contener al menos 3 caracteres validos.")
        if len(value) > 300:
            raise ValueError("La consulta no puede exceder los 300 caracteres.")
        return value


class AISearchRoutingPlan(BaseModel):
    """Contrato interno estricto (Structured Output) devuelto por Gemini para enrutar la consulta."""

    model_config = ConfigDict(extra="forbid")

    tipo_intencion: IntentType = Field(
        ...,
        description=(
            "Clasificacion estricta: 'consulta_estadistica' para estadisticas agregadas disponibles; "
            "'bloqueo_privacidad' si pregunta por una persona, nombre propio, DPI, direccion o caso individual; "
            "'fuera_de_dominio' para temas ajenos (deportes, politica, clima, noticias o indicadores inexistentes)."
        ),
    )
    conjunto_datos: Optional[DatasetId] = Field(
        default=None,
        description="Dataset agregado a consultar cuando tipo_intencion es 'consulta_estadistica'.",
    )
    columnas_metricas: List[AllowedColumn] = Field(
        default_factory=list,
        description="Metricas o columnas especificas relevantes para responder la consulta.",
    )
    codigos_departamento: List[int] = Field(
        default_factory=list,
        description="Codigos numericos INE de departamentos (1 al 22) para filtrar si aplica.",
    )
    codigo_municipio: Optional[str] = Field(
        default=None,
        description="Codigo INE municipal de 4 digitos (ej. '0101') cuando se consulta nivel municipal.",
    )
    region_id: Optional[int] = Field(
        default=None,
        description="Identificador de region socioeconomica (0 para Republica, 1 a 8 para regiones).",
    )
    anio_inicio: Optional[int] = Field(
        default=None,
        description="Anio inicial del filtro temporal (2015 a 2030) si aplica.",
    )
    anio_fin: Optional[int] = Field(
        default=None,
        description="Anio final del filtro temporal (2015 a 2030) si aplica.",
    )
    mes: Optional[int] = Field(
        default=None,
        description="Mes numerico (1 a 12) para series mensuales de canasta basica o IPC.",
    )
    dominio_area: Optional[Literal["Urbana", "Rural"]] = Field(
        default=None,
        description="Filtro de area geografica para canasta basica o proyecciones de costo de vida.",
    )
    tipo_canasta: Optional[Literal["CBA", "CA"]] = Field(
        default=None,
        description="Tipo de canasta: 'CBA' (Basica Alimentaria) o 'CA' (Ampliada).",
    )
    nivel_vulnerabilidad: Optional[Literal["Crítica", "Alta", "Moderada", "Baja"]] = Field(
        default=None,
        description="Filtro por clasificacion de vulnerabilidad territorial si aplica.",
    )
    ordenar_por: Optional[AllowedColumn] = Field(
        default=None,
        description="Columna por la cual ordenar los resultados.",
    )
    direccion_orden: Literal["asc", "desc"] = Field(
        default="desc",
        description="Direccion del ordenamiento: 'desc' de mayor a menor, 'asc' de menor a mayor.",
    )
    limite: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Cantidad maxima de registros agregados a retornar (1 a 50).",
    )
    visualizacion_sugerida: VisualizationKind = Field(
        default="ninguna",
        description="Tipo de visualizacion oficial sugerida que mejor representa la respuesta.",
    )
    mensaje_contextual: Optional[str] = Field(
        default=None,
        description="Resumen breve, objetivo y amable en espanol describiendo que muestran las cifras consultadas.",
    )


class AISearchResponse(BaseModel):
    """Contrato publico de salida sin detalles tecnicos ni estructura interna."""

    model_config = ConfigDict(extra="forbid")

    mensaje: str = Field(
        ...,
        description="Mensaje claro y cortés en espanol dirigido al ciudadano.",
    )
    datos: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Registros estadisticos agregados y anonimizados.",
    )
    visualizacion_url: Optional[str] = Field(
        default=None,
        description="Ruta relativa hacia la visualizacion interactiva relacionada, si aplica.",
    )
