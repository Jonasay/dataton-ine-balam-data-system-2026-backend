from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
from scipy import stats

from src.core.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from src.core.geo_master import DEPARTAMENTOS_INE, ensure_guatemala_geojson
from src.core.human_labels import INTEGER_METRIC_COLUMNS, humanize_label

DATA_PROCESSED = PROCESSED_DATA_DIR
INDICATORS_DIR = DATA_PROCESSED / "indicadores"
ANALYSIS_DIR = DATA_PROCESSED / "analisis"
ECONOMY_DIR = DATA_PROCESSED / "economia"
DEMOGRAPHY_DIR = DATA_PROCESSED / "demografia"
VISUALIZATIONS_DIR = DATA_PROCESSED / "visualizaciones"
CHARTS_CACHE_DIR = VISUALIZATIONS_DIR / "charts"
CHARTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# paleta institucional moderna optimizada para dashboards web
CLUSTER_COLOR_MAP: Dict[str, str] = {
    "Hub Metropolitano y Central": "#38bdf8",
    "Altiplano Rural y Sobrecarga Demográfica": "#f43f5e",
    "Cinturón Agrícola de Alta Expulsión Migratoria": "#f59e0b",
    "Corredor Logístico Costero y Siniestralidad Vial": "#a855f7",
}

VULN_COLOR_MAP: Dict[str, str] = {
    "Crítica": "#ef4444",
    "Alta": "#f97316",
    "Moderada": "#eab308",
    "Baja": "#10b981",
}

# diccionario maestro de metadatos por indicador disponible
INDICATORS_CATALOG: Dict[str, Dict[str, str]] = {
    "indice_vulnerabilidad_ivst": {
        "titulo": "Índice de Vulnerabilidad Socioeconómica Territorial (IVST)",
        "unidad": "Puntos (0-100)",
        "dominio": "Vulnerabilidad",
    },
    "tasa_retorno_migratorio_por_10k": {
        "titulo": "Tasa de Retorno Migratorio por 10,000 Habitantes",
        "unidad": "Retornados / 10k hab",
        "dominio": "Migración",
    },
    "pct_retornados_menores": {
        "titulo": "Proporción de Niñez y Adolescencia Retornada",
        "unidad": "% Menores (<18 años)",
        "dominio": "Migración",
    },
    "pct_retornadas_mujeres": {
        "titulo": "Proporción de Mujeres Retornadas",
        "unidad": "% Mujeres",
        "dominio": "Migración",
    },
    "retornados_total": {
        "titulo": "Total de Personas Migrantes Retornadas (2024)",
        "unidad": "Personas",
        "dominio": "Migración",
    },
    "tasa_necropsias_por_100k": {
        "titulo": "Tasa de Necropsias Médico-Legales INACIF por 100k Hab",
        "unidad": "Necropsias / 100k hab",
        "dominio": "Seguridad",
    },
    "necropsias_total": {
        "titulo": "Total de Necropsias Forenses INACIF",
        "unidad": "Peritajes",
        "dominio": "Seguridad",
    },
    "tasa_victimas_viales_por_100k": {
        "titulo": "Tasa de Víctimas Viales PNC por 100k Habitantes",
        "unidad": "Víctimas / 100k hab",
        "dominio": "Movilidad",
    },
    "tasa_mortalidad_vial_por_100k": {
        "titulo": "Tasa de Mortalidad por Accidentes de Tránsito PNC",
        "unidad": "Fallecidos / 100k hab",
        "dominio": "Movilidad",
    },
    "victimas_viales_total": {
        "titulo": "Total de Víctimas en Hechos de Tránsito (2024)",
        "unidad": "Víctimas",
        "dominio": "Movilidad",
    },
    "tasa_matricula_superior_por_10k": {
        "titulo": "Tasa de Matrícula en Educación Superior por 10k Hab",
        "unidad": "Estudiantes / 10k hab",
        "dominio": "Educación",
    },
    "pct_mujeres_superior": {
        "titulo": "Participación Femenina en Educación Superior",
        "unidad": "% Mujeres",
        "dominio": "Educación",
    },
    "matriculados_superior_total": {
        "titulo": "Matrícula Total en Educación Superior",
        "unidad": "Estudiantes",
        "dominio": "Educación",
    },
    "tasa_natalidad_por_1000": {
        "titulo": "Tasa Bruta de Natalidad (TBN)",
        "unidad": "Nacidos / 1,000 hab",
        "dominio": "Demografía",
    },
    "tasa_mortalidad_por_1000": {
        "titulo": "Tasa Bruta de Mortalidad (TBM)",
        "unidad": "Defunciones / 1,000 hab",
        "dominio": "Demografía",
    },
    "tasa_crecimiento_natural_por_1000": {
        "titulo": "Tasa de Crecimiento Natural (TCN)",
        "unidad": "Saldo / 1,000 hab",
        "dominio": "Demografía",
    },
    "razon_dependencia_demografica": {
        "titulo": "Razón de Dependencia Demográfica",
        "unidad": "Dependientes / 100 act.",
        "dominio": "Demografía",
    },
    "indice_masculinidad": {
        "titulo": "Índice de Masculinidad",
        "unidad": "Hombres / 100 mujeres",
        "dominio": "Demografía",
    },
    "poblacion_total": {
        "titulo": "Población Total Proyectada (2024)",
        "unidad": "Habitantes",
        "dominio": "Demografía",
    },
    "inflacion_regional_interanual": {
        "titulo": "Inflación Regional Interanual del IPC",
        "unidad": "Variación %",
        "dominio": "Economía",
    },
}


def get_indicator_meta(indicator: str) -> Dict[str, str]:
    # obtener titulo legible y unidad de un indicador o generar respaldo limpio
    if indicator in INDICATORS_CATALOG:
        return INDICATORS_CATALOG[indicator]
    clean = indicator.replace("_", " ").capitalize()
    return {"titulo": clean, "unidad": "Valor", "dominio": "General"}


def load_enriched_department_df() -> pd.DataFrame:
    # cargar indicadores departamentales enriquecidos con clusters pca e indice ivst
    ind_path = INDICATORS_DIR / "indicadores_consolidados_departamentales_2024.parquet"
    if not ind_path.exists():
        raise FileNotFoundError(f"no se encontro el dataset de indicadores: {ind_path}")

    df_ind = pl.read_parquet(ind_path)
    pdf = df_ind.to_pandas()

    clust_path = ANALYSIS_DIR / "clusters_departamentales.parquet"
    vuln_path = ANALYSIS_DIR / "vulnerabilidad_departamental.parquet"

    if not clust_path.exists() or not vuln_path.exists():
        from src.analysis.data_science import run_full_data_science_pipeline
        run_full_data_science_pipeline()

    if clust_path.exists():
        c_pdf = pl.read_parquet(clust_path).to_pandas()[
            ["depto_codigo", "cluster_id", "cluster_nombre", "pca_1", "pca_2", "pca_3"]
        ]
        pdf = pdf.merge(c_pdf, on="depto_codigo", how="left")

    if vuln_path.exists():
        v_pdf = pl.read_parquet(vuln_path).to_pandas()[
            ["depto_codigo", "ranking", "indice_vulnerabilidad_ivst", "nivel_vulnerabilidad"]
        ]
        pdf = pdf.merge(v_pdf, on="depto_codigo", how="left")

    pdf["cod"] = pdf["depto_codigo"].astype(int).astype(str).str.zfill(2)
    return pdf


def load_enriched_geo_dataframe(indicator: str = "tasa_retorno_migratorio_por_10k") -> Tuple[Any, Dict[str, str]]:
    # unir capa geojson departamental con el conjunto enriquecido de indicadores
    from src.process.process import load_geodata

    geo_path = ensure_guatemala_geojson().resolve()
    geo_gdf = load_geodata(geo_path, target_crs=4326, code_col="COD_COLUMNA")
    enriched_df = load_enriched_department_df()

    if indicator not in enriched_df.columns:
        raise ValueError(f"indicador '{indicator}' no existe en el repositorio departamental")

    # evitar colision de columnas espaciales conservando nombre oficial
    cols_to_merge = [
        c for c in enriched_df.columns
        if c not in ["nombre", "geometry"] and (c == "cod" or c not in geo_gdf.columns)
    ]
    merged_gdf = geo_gdf.merge(enriched_df[cols_to_merge], on="cod", how="left")
    merged_gdf[indicator] = merged_gdf[indicator].fillna(0.0)
    if "nombre" not in merged_gdf.columns and "depto_nombre" in merged_gdf.columns:
        merged_gdf["nombre"] = merged_gdf["depto_nombre"]

    return merged_gdf, get_indicator_meta(indicator)


def _apply_standard_layout(fig: go.Figure, title: str, subtitle: str = "", height: int = 560) -> go.Figure:
    # aplicar tema visual moderno consistente y tipografia limpia para el frontend
    full_title = f"<b>{title}</b>"
    if subtitle:
        full_title += f"<br><span style='font-size:12px;color:#94a3b8;'>{subtitle}</span>"

    fig.update_layout(
        template="plotly_dark",
        title=dict(text=full_title, x=0.02, y=0.96, font=dict(size=16, color="#f8fafc")),
        paper_bgcolor="#0b1120",
        plot_bgcolor="#0f172a",
        font=dict(family="Inter, Liberation Sans, Arial, sans-serif", color="#e2e8f0", size=12),
        height=height,
        margin=dict(l=55, r=30, t=80, b=50),
        legend=dict(
            bgcolor="rgba(15, 23, 42, 0.78)",
            bordercolor="#334155",
            borderwidth=1,
            font=dict(size=11),
        ),
        hoverlabel=dict(bgcolor="#0f172a", bordercolor="#38bdf8", font=dict(color="#f8fafc", size=12)),
    )
    return fig


def _serialize_figure(
    fig: go.Figure,
    chart_id: str,
    title: str,
    subtitle: str,
    chart_type: str,
    summary_data: Dict[str, Any],
    output_format: str = "html",
) -> Union[Dict[str, Any], str]:
    # unificar salida en especificacion json serializable o pagina html interactiva
    if output_format.lower().strip() == "html":
        if chart_type in {"bar", "bar_municipal"}:
            fig_h = int(fig.layout.height or 680)
            raw_html = fig.to_html(
                full_html=True,
                include_plotlyjs="cdn",
                default_width="100%",
                default_height=f"{fig_h}px",
                config={"responsive": True, "displaylogo": False},
            )
            full_bleed_css = (
                "<style>"
                "html, body { margin: 0; padding: 0; background: #0b1120; width: 100%; min-height: 100%; overflow-x: hidden; overflow-y: auto; }"
                f".plotly-graph-div {{ width: 100% !important; height: {fig_h}px !important; }}"
                "</style>"
            )
        else:
            raw_html = fig.to_html(
                full_html=True,
                include_plotlyjs="cdn",
                default_width="100%",
                default_height="100vh",
                config={"responsive": True, "displaylogo": False},
            )
            full_bleed_css = (
                "<style>"
                "html, body { margin: 0; padding: 0; background: #0b1120; width: 100%; height: 100%; overflow: hidden; }"
                ".plotly-graph-div { width: 100% !important; height: 100vh !important; }"
                "</style>"
            )
        if "</head>" in raw_html:
            return raw_html.replace("</head>", f"{full_bleed_css}</head>")
        return full_bleed_css + raw_html

    plotly_spec = json.loads(fig.to_json())
    return {
        "chart_id": chart_id,
        "titulo": title,
        "subtitulo": subtitle,
        "tipo_grafica": chart_type,
        "datos_resumen": summary_data,
        "plotly_spec": plotly_spec,
    }


def get_or_build_chart(
    cache_key: str,
    output_format: str,
    builder_fn: Any,
    force_refresh: bool = False,
) -> Union[Dict[str, Any], str]:
    # leer grafica precalculada desde disco o generar y persistir en cache
    fmt = "html" if output_format.lower().strip() == "html" else "json"
    CHARTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CHARTS_CACHE_DIR / f"{cache_key}.{fmt}"

    if not force_refresh and cache_file.exists() and cache_file.stat().st_size > 0:
        if fmt == "html":
            return cache_file.read_text(encoding="utf-8")
        return json.loads(cache_file.read_text(encoding="utf-8"))

    result = builder_fn(output_format=fmt)
    if fmt == "html" and isinstance(result, str):
        cache_file.write_text(result, encoding="utf-8")
    elif isinstance(result, dict):
        cache_file.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def build_3d_demographic_trajectory_chart(
    color_by: str = "region_nombre",
    output_format: str = "json",
) -> Union[Dict[str, Any], str]:
    # grafica 3d animada con movimiento de los 22 departamentos entre 2015 y 2030
    traj_path = ANALYSIS_DIR / "trayectoria_demografica_anual.parquet"
    if not traj_path.exists():
        from src.analysis.data_science import compute_yearly_demographic_trajectory
        compute_yearly_demographic_trajectory()

    df_traj = pl.read_parquet(traj_path).to_pandas()
    enriched = load_enriched_department_df()[["depto_codigo", "cluster_nombre", "nivel_vulnerabilidad"]]
    df_traj = df_traj.merge(enriched, on="depto_codigo", how="left")

    active_color = color_by if color_by in df_traj.columns else "region_nombre"
    color_discrete = CLUSTER_COLOR_MAP if active_color == "cluster_nombre" else (
        VULN_COLOR_MAP if active_color == "nivel_vulnerabilidad" else None
    )

    fig = px.scatter_3d(
        df_traj,
        x="razon_dependencia_demografica",
        y="indice_masculinidad",
        z="pct_poblacion_menor_15",
        animation_frame="anio",
        animation_group="depto_nombre",
        size="poblacion_total",
        size_max=34,
        color=active_color,
        color_discrete_map=color_discrete,
        hover_name="depto_nombre",
        hover_data={
            "anio": True,
            "poblacion_total": ":,",
            "razon_dependencia_demografica": ":.2f",
            "indice_masculinidad": ":.2f",
            "pct_poblacion_menor_15": ":.2f",
            "pct_poblacion_65_mas": ":.2f",
        },
        range_x=[40, 82],
        range_y=[86, 108],
        range_z=[21, 43],
        labels={
            "razon_dependencia_demografica": "Dependencia Demográfica (%)",
            "indice_masculinidad": "Índice Masculinidad (H/100M)",
            "pct_poblacion_menor_15": "Población <15 años (%)",
            "anio": "Año",
        },
    )

    # agregar estelas de trayectoria continua 2015-2030 para mostrar direccion del movimiento
    for depto_name, grp in df_traj.groupby("depto_nombre"):
        grp_sorted = grp.sort_values("anio")
        fig.add_trace(
            go.Scatter3d(
                x=grp_sorted["razon_dependencia_demografica"],
                y=grp_sorted["indice_masculinidad"],
                z=grp_sorted["pct_poblacion_menor_15"],
                mode="lines",
                line=dict(color="rgba(148, 163, 184, 0.25)", width=2),
                name=f"Ruta {depto_name}",
                showlegend=False,
                hoverinfo="skip",
            )
        )

    title = "Trayectoria Demográfica 3D Animada por Departamento (2015–2030)"
    subtitle = "Movimiento temporal de dependencia demográfica, razón de sexo y juventud poblacional (proyecciones oficiales INE)"
    _apply_standard_layout(fig, title, subtitle, height=640)
    fig.update_layout(
        scene=dict(
            xaxis=dict(title="Dependencia (%)", backgroundcolor="#0f172a", gridcolor="#1e293b"),
            yaxis=dict(title="Masculinidad (H/100M)", backgroundcolor="#0f172a", gridcolor="#1e293b"),
            zaxis=dict(title="% Menores de 15 años", backgroundcolor="#0f172a", gridcolor="#1e293b"),
            camera=dict(eye=dict(x=1.55, y=-1.55, z=1.05)),
        ),
        updatemenus=[
            dict(
                type="buttons",
                showactive=False,
                x=0.05,
                y=0.02,
                bgcolor="#1e293b",
                bordercolor="#38bdf8",
                font=dict(color="#f8fafc"),
            )
        ],
    )

    summary = {
        "anios_cubiertos": "2015-2030",
        "total_puntos_trayectoria": len(df_traj),
        "eje_x": "razon_dependencia_demografica",
        "eje_y": "indice_masculinidad",
        "eje_z": "pct_poblacion_menor_15",
    }
    return _serialize_figure(fig, "3d_trayectoria_demografica", title, subtitle, "scatter_3d_animated", summary, output_format)


def build_3d_pca_clusters_chart(output_format: str = "json") -> Union[Dict[str, Any], str]:
    # espacio 3d de componentes principales pca y centroides k-means
    pdf = load_enriched_department_df()

    fig = px.scatter_3d(
        pdf,
        x="pca_1",
        y="pca_2",
        z="pca_3",
        color="cluster_nombre",
        color_discrete_map=CLUSTER_COLOR_MAP,
        size="indice_vulnerabilidad_ivst",
        size_max=28,
        text="depto_nombre",
        hover_name="depto_nombre",
        hover_data={
            "region_nombre": True,
            "indice_vulnerabilidad_ivst": ":.2f",
            "nivel_vulnerabilidad": True,
            "tasa_retorno_migratorio_por_10k": ":.2f",
            "tasa_necropsias_por_100k": ":.2f",
            "tasa_matricula_superior_por_10k": ":.2f",
        },
        labels={
            "pca_1": "PC1: Urbanización y Vialidad (50.0%)",
            "pca_2": "PC2: Expulsión Migratoria (19.1%)",
            "pca_3": "PC3: Fecundidad vs Inflación (10.9%)",
            "cluster_nombre": "Conglomerado K-Means",
        },
    )
    fig.update_traces(textposition="top center", textfont=dict(size=10, color="#f8fafc"))

    # agregar centroides geometricos en 3d para cada conglomerado
    centroids = pdf.groupby("cluster_nombre")[["pca_1", "pca_2", "pca_3"]].mean().reset_index()
    fig.add_trace(
        go.Scatter3d(
            x=centroids["pca_1"],
            y=centroids["pca_2"],
            z=centroids["pca_3"],
            mode="markers",
            marker=dict(size=11, symbol="diamond", color="#ffffff", line=dict(color="#38bdf8", width=2)),
            name="Centroides K-Means",
            hovertext=[f"Centroide: {n}" for n in centroids["cluster_nombre"]],
            hoverinfo="text",
        )
    )

    title = "Espacio Multivariado 3D: Componentes Principales (PCA) y Conglomerados"
    subtitle = "80.0% de varianza explicada acumulada sobre 22 departamentos (tamaño proporcional al índice IVST)"
    _apply_standard_layout(fig, title, subtitle, height=640)
    fig.update_layout(
        scene=dict(
            xaxis=dict(backgroundcolor="#0f172a", gridcolor="#1e293b"),
            yaxis=dict(backgroundcolor="#0f172a", gridcolor="#1e293b"),
            zaxis=dict(backgroundcolor="#0f172a", gridcolor="#1e293b"),
            camera=dict(eye=dict(x=1.45, y=1.45, z=1.15)),
        )
    )

    summary = {
        "varianza_acumulada_pct": 80.0,
        "total_clusters": int(pdf["cluster_id"].nunique()),
        "departamentos": len(pdf),
    }
    return _serialize_figure(fig, "3d_clusters_pca", title, subtitle, "scatter_3d", summary, output_format)


def build_3d_multidimensional_scatter_chart(
    x_col: str = "tasa_retorno_migratorio_por_10k",
    y_col: str = "tasa_matricula_superior_por_10k",
    z_col: str = "tasa_necropsias_por_100k",
    color_col: str = "nivel_vulnerabilidad",
    size_col: str = "poblacion_total",
    output_format: str = "json",
) -> Union[Dict[str, Any], str]:
    # cubo de dispersion 3d personalizable para analizar comportamiento cruzado de indicadores
    pdf = load_enriched_department_df()
    for col in [x_col, y_col, z_col, size_col]:
        if col not in pdf.columns:
            raise ValueError(f"columna '{col}' no disponible en indicadores departamentales")

    x_meta = get_indicator_meta(x_col)
    y_meta = get_indicator_meta(y_col)
    z_meta = get_indicator_meta(z_col)

    color_map = VULN_COLOR_MAP if color_col == "nivel_vulnerabilidad" else (
        CLUSTER_COLOR_MAP if color_col == "cluster_nombre" else None
    )

    fig = px.scatter_3d(
        pdf,
        x=x_col,
        y=y_col,
        z=z_col,
        color=color_col if color_col in pdf.columns else "nivel_vulnerabilidad",
        color_discrete_map=color_map,
        size=size_col,
        size_max=30,
        text="depto_nombre",
        hover_name="depto_nombre",
        hover_data={
            "region_nombre": True,
            "indice_vulnerabilidad_ivst": ":.2f",
            x_col: ":.2f",
            y_col: ":.2f",
            z_col: ":.2f",
        },
        labels={
            x_col: x_meta["titulo"],
            y_col: y_meta["titulo"],
            z_col: z_meta["titulo"],
        },
    )
    fig.update_traces(textposition="top center", textfont=dict(size=9, color="#f8fafc"))

    title = f"Análisis 3D Multidimensional: {x_meta['dominio']} × {y_meta['dominio']} × {z_meta['dominio']}"
    subtitle = f"X: {x_meta['titulo']} | Y: {y_meta['titulo']} | Z: {z_meta['titulo']}"
    _apply_standard_layout(fig, title, subtitle, height=640)
    fig.update_layout(
        scene=dict(
            xaxis=dict(title=x_meta["unidad"], backgroundcolor="#0f172a", gridcolor="#1e293b"),
            yaxis=dict(title=y_meta["unidad"], backgroundcolor="#0f172a", gridcolor="#1e293b"),
            zaxis=dict(title=z_meta["unidad"], backgroundcolor="#0f172a", gridcolor="#1e293b"),
        )
    )

    return _serialize_figure(
        fig,
        "3d_riesgo_multidimensional",
        title,
        subtitle,
        "scatter_3d",
        {"x": x_col, "y": y_col, "z": z_col, "color": color_col},
        output_format,
    )


def build_3d_cost_of_living_trajectory_chart(output_format: str = "json") -> Union[Dict[str, Any], str]:
    # trayectoria 3d mensual de evolucion del costo de vida urbano, rural y brecha monetaria
    basket_path = ECONOMY_DIR / "canasta_basica_mensual.parquet"
    if not basket_path.exists():
        raise FileNotFoundError(f"no se encontro archivo de canasta basica en: {basket_path}")

    df_cba = pl.read_parquet(basket_path).filter(pl.col("tipo_canasta") == "CBA").to_pandas()
    pivoted = df_cba.pivot(index=["anio", "mes"], columns="dominio", values="costo_mensual_percapita").reset_index()
    pivoted = pivoted.sort_values(["anio", "mes"]).reset_index(drop=True)
    pivoted["mes_continuo"] = np.arange(1, len(pivoted) + 1)
    pivoted["periodo"] = pivoted.apply(lambda r: f"{int(r['anio'])}-{int(r['mes']):02d}", axis=1)
    pivoted["brecha_gtq"] = (pivoted["Urbana"] - pivoted["Rural"]).round(2)

    fig = go.Figure()
    # linea de trayectoria historica continua
    fig.add_trace(
        go.Scatter3d(
            x=pivoted["mes_continuo"],
            y=pivoted["Urbana"],
            z=pivoted["Rural"],
            mode="lines+markers",
            line=dict(color=pivoted["brecha_gtq"], colorscale="Turbo", width=6),
            marker=dict(
                size=6,
                color=pivoted["brecha_gtq"],
                colorscale="Turbo",
                colorbar=dict(title="Brecha (Q)"),
                showscale=True,
            ),
            text=pivoted["periodo"],
            customdata=pivoted[["brecha_gtq"]],
            hovertemplate=(
                "<b>Periodo: %{text}</b><br>"
                "CBA Urbana: Q%{y:,.2f}<br>"
                "CBA Rural: Q%{z:,.2f}<br>"
                "Brecha U-R: Q%{customdata[0]:,.2f}<extra></extra>"
            ),
            name="Trayectoria CBA",
        )
    )

    # generar cuadros animados acumulados para visualizar movimiento temporal mes a mes
    frames = []
    for idx in range(len(pivoted)):
        sub = pivoted.iloc[: idx + 1]
        cur = pivoted.iloc[idx]
        frames.append(
            go.Frame(
                data=[
                    go.Scatter3d(
                        x=sub["mes_continuo"],
                        y=sub["Urbana"],
                        z=sub["Rural"],
                        mode="lines+markers",
                        line=dict(color="#38bdf8", width=6),
                        marker=dict(size=5, color=sub["brecha_gtq"], colorscale="Turbo"),
                        text=sub["periodo"],
                    ),
                    go.Scatter3d(
                        x=[cur["mes_continuo"]],
                        y=[cur["Urbana"]],
                        z=[cur["Rural"]],
                        mode="markers",
                        marker=dict(size=11, color="#f43f5e", symbol="diamond"),
                        name="Mes Actual",
                    ),
                ],
                name=cur["periodo"],
            )
        )

    last_row = pivoted.iloc[-1]
    fig.add_trace(
        go.Scatter3d(
            x=[last_row["mes_continuo"]],
            y=[last_row["Urbana"]],
            z=[last_row["Rural"]],
            mode="markers",
            marker=dict(size=11, color="#f43f5e", symbol="diamond"),
            name="Punto Actual",
        )
    )
    fig.frames = frames

    title = "Trayectoria 3D Animada del Costo de la Canasta Básica Alimentaria (2024–2026)"
    subtitle = "Desplazamiento mensual simultáneo del costo per cápita Urbano (Y), Rural (Z) y Brecha Monetaria"
    _apply_standard_layout(fig, title, subtitle, height=640)
    fig.update_layout(
        scene=dict(
            xaxis=dict(title="Mes Continuo", range=[0, len(pivoted) + 2], backgroundcolor="#0f172a", gridcolor="#1e293b"),
            yaxis=dict(title="CBA Urbana (GTQ)", backgroundcolor="#0f172a", gridcolor="#1e293b"),
            zaxis=dict(title="CBA Rural (GTQ)", backgroundcolor="#0f172a", gridcolor="#1e293b"),
        ),
        updatemenus=[
            dict(
                type="buttons",
                x=0.05,
                y=0.02,
                bgcolor="#1e293b",
                bordercolor="#38bdf8",
                buttons=[
                    dict(label="▶ Reproducir Trayectoria", method="animate", args=[None, {"frame": {"duration": 140, "redraw": True}, "fromcurrent": True}]),
                    dict(label="⏸ Pausar", method="animate", args=[[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}]),
                ],
            )
        ],
    )

    summary = {
        "meses_observados": len(pivoted),
        "cba_urbana_inicial": round(float(pivoted["Urbana"].iloc[0]), 2),
        "cba_urbana_final": round(float(pivoted["Urbana"].iloc[-1]), 2),
        "brecha_final_gtq": float(pivoted["brecha_gtq"].iloc[-1]),
    }
    return _serialize_figure(fig, "3d_trayectoria_costo_vida", title, subtitle, "scatter_3d_trajectory", summary, output_format)


def build_department_ranking_bar_chart(
    indicator: str = "tasa_retorno_migratorio_por_10k",
    top_n: int = 22,
    order: str = "desc",
    orientation: str = "h",
    color_by: str = "nivel_vulnerabilidad",
    output_format: str = "json",
) -> Union[Dict[str, Any], str]:
    # grafica de barras interactiva con ranking departamental y linea de promedio nacional
    pdf = load_enriched_department_df()
    if indicator not in pdf.columns:
        raise ValueError(f"indicador '{indicator}' no encontrado")

    meta = get_indicator_meta(indicator)
    ascending = order.lower() == "asc"
    sorted_df = pdf.sort_values(indicator, ascending=ascending).head(top_n)
    if orientation == "h":
        sorted_df = sorted_df.iloc[::-1]

    is_int_metric = indicator in INTEGER_METRIC_COLUMNS
    text_tpl = "%{text:,.0f}" if is_int_metric else "%{text:,.2f}"
    national_mean = float(pdf[indicator].mean())
    mean_txt = f"{national_mean:,.0f}" if is_int_metric else f"{national_mean:,.2f}"

    active_color = color_by if color_by in sorted_df.columns else "nivel_vulnerabilidad"
    legend_title = humanize_label(active_color)
    color_map = VULN_COLOR_MAP if active_color == "nivel_vulnerabilidad" else (
        CLUSTER_COLOR_MAP if active_color == "cluster_nombre" else None
    )

    n_bars = len(sorted_df)
    dyn_height = (max(680, 152 + n_bars * 24) if n_bars >= 20 else max(420, 180 + n_bars * 26)) if orientation == "h" else 520

    max_val = float(sorted_df[indicator].max()) if n_bars > 0 else 1.0
    min_val = float(sorted_df[indicator].min()) if n_bars > 0 else 0.0
    axis_low = min(0.0, min_val * 1.18)
    axis_high = max(max_val, national_mean) * 1.18 if max(max_val, national_mean) > 0 else 1.0

    if orientation == "h":
        fig = px.bar(
            sorted_df,
            x=indicator,
            y="depto_nombre",
            orientation="h",
            color=active_color,
            color_discrete_map=color_map,
            text=indicator,
            hover_data={"region_nombre": True, "poblacion_total": ":,", "indice_vulnerabilidad_ivst": ":.2f"},
            labels={indicator: meta["unidad"], "depto_nombre": "Departamento", active_color: legend_title},
        )
        fig.add_vline(
            x=national_mean,
            line_dash="dash",
            line_color="#38bdf8",
            line_width=1.8,
        )
        fig.add_annotation(
            x=national_mean,
            xref="x",
            y=1.04,
            yref="paper",
            yanchor="bottom",
            showarrow=False,
            text=f"Media Nacional: {mean_txt}",
            font=dict(color="#38bdf8", size=11),
        )
    else:
        fig = px.bar(
            sorted_df,
            x="depto_nombre",
            y=indicator,
            color=active_color,
            color_discrete_map=color_map,
            text=indicator,
            hover_data={"region_nombre": True, "poblacion_total": ":,", "indice_vulnerabilidad_ivst": ":.2f"},
            labels={indicator: meta["unidad"], "depto_nombre": "Departamento", active_color: legend_title},
        )
        fig.add_hline(
            y=national_mean,
            line_dash="dash",
            line_color="#38bdf8",
            annotation_text=f"Media Nacional: {mean_txt}",
        )

    fig.update_traces(texttemplate=text_tpl, textposition="outside", cliponaxis=False)
    title = f"Ranking Departamental: {meta['titulo']}"
    subtitle = f"Comparativa territorial ({n_bars} departamentos) | Unidad: {meta['unidad']}"
    _apply_standard_layout(fig, title, subtitle, height=dyn_height)

    if orientation == "h":
        y_order = "total descending" if ascending else "total ascending"
        fig.update_layout(
            margin=dict(l=65, r=110, t=90, b=55),
            legend_title_text=legend_title,
            xaxis=dict(range=[axis_low, axis_high]),
            yaxis=dict(categoryorder=y_order, automargin=True),
        )
    else:
        fig.update_layout(legend_title_text=legend_title)

    summary = {
        "indicador": indicator,
        "media_nacional": round(national_mean, 2),
        "max_depto": str(pdf.sort_values(indicator, ascending=False).iloc[0]["depto_nombre"]),
        "max_valor": round(float(pdf[indicator].max()), 2),
    }
    return _serialize_figure(fig, f"barras_{indicator}", title, subtitle, "bar", summary, output_format)


def build_municipal_ranking_bar_chart(
    indicator: str = "tasa_necropsias_por_100k",
    depto_codigo: Optional[int] = None,
    top_n: int = 20,
    output_format: str = "json",
) -> Union[Dict[str, Any], str]:
    # grafica de barras interactiva a escala municipal sobre los 340 municipios
    mup_path = INDICATORS_DIR / "indicadores_consolidados_municipales_2024.parquet"
    if not mup_path.exists():
        raise FileNotFoundError(f"no se encontro dataset municipal en: {mup_path}")

    df_mup = pl.read_parquet(mup_path)
    if depto_codigo is not None:
        df_mup = df_mup.filter(pl.col("depto_codigo") == depto_codigo)

    if indicator not in df_mup.columns:
        raise ValueError(f"indicador municipal '{indicator}' no disponible")

    pdf = df_mup.to_pandas()
    pdf["etiqueta_muni"] = pdf.apply(lambda r: f"{r['mupio_codigo_str']} ({r['depto_nombre']})", axis=1)
    top_df = pdf.sort_values(indicator, ascending=False).head(top_n).iloc[::-1]
    meta = get_indicator_meta(indicator)

    is_int_metric = indicator in INTEGER_METRIC_COLUMNS
    text_tpl = "%{text:,.0f}" if is_int_metric else "%{text:,.2f}"
    n_bars = len(top_df)
    dyn_height = max(680, 152 + n_bars * 24) if n_bars >= 20 else max(420, 180 + n_bars * 26)
    max_val = float(top_df[indicator].max()) if n_bars > 0 else 1.0
    min_val = float(top_df[indicator].min()) if n_bars > 0 else 0.0

    fig = px.bar(
        top_df,
        x=indicator,
        y="etiqueta_muni",
        orientation="h",
        color="depto_nombre",
        text=indicator,
        hover_data={"poblacion_total": ":,", "mupio_codigo_str": True},
        labels={indicator: meta["unidad"], "etiqueta_muni": "Municipio (Código INE)", "depto_nombre": "Departamento"},
    )
    fig.update_traces(texttemplate=text_tpl, textposition="outside", cliponaxis=False)

    scope_txt = DEPARTAMENTOS_INE[depto_codigo]["nombre"] if depto_codigo in DEPARTAMENTOS_INE else "República de Guatemala"
    title = f"Top {n_bars} Municipios: {meta['titulo']} ({scope_txt})"
    subtitle = "Desagregación local sobre los 340 municipios oficiales con denominador demográfico INE"
    _apply_standard_layout(fig, title, subtitle, height=dyn_height)
    fig.update_layout(
        margin=dict(l=70, r=110, t=90, b=55),
        legend_title_text="Departamento",
        xaxis=dict(range=[min(0.0, min_val * 1.18), max_val * 1.18 if max_val > 0 else 1.0]),
        yaxis=dict(categoryorder="total ascending", automargin=True),
    )

    return _serialize_figure(
        fig,
        f"barras_municipales_{indicator}",
        title,
        subtitle,
        "bar_municipal",
        {"alcance": scope_txt, "total_municipios_evaluados": len(pdf)},
        output_format,
    )


def build_demographic_structure_stacked_bar_chart(output_format: str = "json") -> Union[Dict[str, Any], str]:
    # barras apiladas 100% de estructura etaria y sobrecarga de dependencia demografica
    pdf = load_enriched_department_df().sort_values("razon_dependencia_demografica", ascending=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=pdf["depto_nombre"], x=pdf["pct_poblacion_menor_15"],
        name="Niñez (< 15 años)", orientation="h", marker_color="#f43f5e",
        hovertemplate="%{y}: %{x:.2f}% (<15 años)<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=pdf["depto_nombre"], x=pdf["pct_poblacion_15_64"],
        name="Edad Productiva (15–64 años)", orientation="h", marker_color="#0ea5e9",
        hovertemplate="%{y}: %{x:.2f}% (15–64 años)<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=pdf["depto_nombre"], x=pdf["pct_poblacion_65_mas"],
        name="Adulto Mayor (65+ años)", orientation="h", marker_color="#f59e0b",
        hovertemplate="%{y}: %{x:.2f}% (65+ años)<extra></extra>",
    ))

    title = "Estructura Etaria Poblacional Apilada por Departamento (2024)"
    subtitle = "Ordenado por Razón de Dependencia Demográfica (Huehuetenango 72.5% vs Sacatepéquez 43.9%)"
    _apply_standard_layout(fig, title, subtitle, height=640)
    fig.update_layout(barmode="stack", xaxis_title="Porcentaje de Población Total (%)", xaxis=dict(range=[0, 100]))

    return _serialize_figure(fig, "barras_estructura_etaria", title, subtitle, "stacked_bar", {"departamentos": len(pdf)}, output_format)


def build_returnees_composition_bar_chart(top_n: int = 12, output_format: str = "json") -> Union[Dict[str, Any], str]:
    # barras agrupadas de composicion de migrantes retornados por edad y genero
    pdf = load_enriched_department_df().sort_values("retornados_total", ascending=False).head(top_n)
    pdf["retornados_adultos"] = (pdf["retornados_total"] - pdf["retornados_menores"]).clip(lower=0)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=pdf["depto_nombre"], y=pdf["retornados_menores"],
        name="Menores de Edad (<18)", marker_color="#f43f5e",
    ))
    fig.add_trace(go.Bar(
        x=pdf["depto_nombre"], y=pdf["retornados_adultos"],
        name="Adultos (>=18)", marker_color="#38bdf8",
    ))
    fig.add_trace(go.Bar(
        x=pdf["depto_nombre"], y=pdf["retornados_mujeres"],
        name="Mujeres Retornadas", marker_color="#a855f7",
    ))

    title = f"Composición Demográfica de Población Retornada (Top {top_n} Departamentos, 2024)"
    subtitle = "Comparación entre niñez/adolescencia devuelta (<18 años), adultos y mujeres"
    _apply_standard_layout(fig, title, subtitle, height=560)
    fig.update_layout(barmode="group", yaxis_title="Personas Retornadas")

    return _serialize_figure(fig, "barras_composicion_retornados", title, subtitle, "grouped_bar", {"top_n": top_n}, output_format)


def build_pie_distribution_chart(
    chart_type: str = "clusters",
    depto_codigo: Optional[int] = None,
    metric: str = "poblacion_total",
    output_format: str = "json",
) -> Union[Dict[str, Any], str]:
    # generador unificado de graficas de pastel, dona y sunburst jerarquico
    pdf = load_enriched_department_df()
    scope_name = "República de Guatemala"
    if depto_codigo is not None:
        filtered = pdf[pdf["depto_codigo"] == depto_codigo]
        if len(filtered) == 0:
            raise ValueError(f"departamento {depto_codigo} no encontrado")
        scope_name = str(filtered.iloc[0]["depto_nombre"])
    else:
        filtered = pdf

    c_type = chart_type.lower().strip()

    if c_type == "clusters":
        grouped = pdf.groupby("cluster_nombre")[metric if metric in pdf.columns else "poblacion_total"].sum().reset_index()
        val_col = grouped.columns[1]
        fig = px.pie(
            grouped, names="cluster_nombre", values=val_col, hole=0.45,
            color="cluster_nombre", color_discrete_map=CLUSTER_COLOR_MAP,
        )
        title = f"Distribución por Conglomerado Socioeconómico ({get_indicator_meta(val_col)['titulo']})"
        subtitle = "Participación porcentual de los 4 clústeres territoriales K-Means"
        summary = grouped.set_index("cluster_nombre")[val_col].to_dict()

    elif c_type == "retornados_edad":
        menores = int(filtered["retornados_menores"].sum())
        adultos = max(int(filtered["retornados_total"].sum()) - menores, 0)
        fig = go.Figure(data=[go.Pie(
            labels=["Menores de Edad (<18 años)", "Adultos (>=18 años)"],
            values=[menores, adultos],
            hole=0.5,
            marker=dict(colors=["#f43f5e", "#0ea5e9"]),
            textinfo="label+percent+value",
        )])
        title = f"Proporción de Niñez y Adolescencia Retornada ({scope_name}, 2024)"
        subtitle = "Identificación del peso etario de menores en flujos migratorios devueltos"
        summary = {"menores": menores, "adultos": adultos}

    elif c_type == "retornados_genero":
        hombres = int(filtered["retornados_hombres"].sum())
        mujeres = int(filtered["retornados_mujeres"].sum())
        fig = go.Figure(data=[go.Pie(
            labels=["Hombres Retornados", "Mujeres Retornadas"],
            values=[hombres, mujeres],
            hole=0.5,
            marker=dict(colors=["#38bdf8", "#ec4899"]),
            textinfo="label+percent+value",
        )])
        title = f"Distribución por Sexo en Población Retornada ({scope_name}, 2024)"
        subtitle = "Perfil demográfico por género del Instituto Guatemalteco de Migración / INE"
        summary = {"hombres": hombres, "mujeres": mujeres}

    elif c_type == "educacion_genero":
        total_est = int(filtered["matriculados_superior_total"].sum())
        pct_m = float(filtered["pct_mujeres_superior"].mean()) if len(filtered) == 1 else float(
            (filtered["matriculados_superior_total"] * filtered["pct_mujeres_superior"] / 100.0).sum() / max(total_est, 1) * 100.0
        )
        mujeres = int(round(total_est * pct_m / 100.0))
        hombres = max(total_est - mujeres, 0)
        fig = go.Figure(data=[go.Pie(
            labels=["Mujeres Matriculadas", "Hombres Matriculados"],
            values=[mujeres, hombres],
            hole=0.5,
            marker=dict(colors=["#a855f7", "#3b82f6"]),
            textinfo="label+percent+value",
        )])
        title = f"Paridad de Género en Educación Superior ({scope_name}, 2025)"
        subtitle = "Matrícula universitaria oficial INE desagregada por sexo"
        summary = {"mujeres": mujeres, "hombres": hombres, "total": total_est}

    elif c_type == "victimas_viales":
        fallecidos = int(filtered["fallecidos_viales_total"].sum())
        lesionados = int(filtered["lesionados_viales_total"].sum())
        fig = go.Figure(data=[go.Pie(
            labels=["Lesionados Viales", "Fallecidos Viales"],
            values=[lesionados, fallecidos],
            hole=0.5,
            marker=dict(colors=["#f59e0b", "#ef4444"]),
            textinfo="label+percent+value",
        )])
        title = f"Severidad de Siniestralidad Vial PNC ({scope_name}, 2024)"
        subtitle = "Proporción de fallecidos in situ frente a lesionados en hechos de tránsito"
        summary = {"fallecidos": fallecidos, "lesionados": lesionados}

    elif c_type == "estructura_etaria":
        p_menor = float((filtered["poblacion_total"] * filtered["pct_poblacion_menor_15"] / 100.0).sum())
        p_act = float((filtered["poblacion_total"] * filtered["pct_poblacion_15_64"] / 100.0).sum())
        p_mayor = float((filtered["poblacion_total"] * filtered["pct_poblacion_65_mas"] / 100.0).sum())
        fig = go.Figure(data=[go.Pie(
            labels=["Niñez (<15 años)", "Edad Productiva (15–64)", "Adulto Mayor (65+)"],
            values=[round(p_menor), round(p_act), round(p_mayor)],
            hole=0.48,
            marker=dict(colors=["#f43f5e", "#10b981", "#f59e0b"]),
            textinfo="label+percent+value",
        )])
        title = f"Pirámide Resumida por Grandes Grupos de Edad ({scope_name}, 2024)"
        subtitle = "Distribución funcional para evaluación del bono demográfico"
        summary = {"menor_15": round(p_menor), "edad_15_64": round(p_act), "mayor_65": round(p_mayor)}

    elif c_type == "jerarquia_territorial":
        val_metric = metric if metric in pdf.columns else "poblacion_total"
        fig = px.sunburst(
            pdf,
            path=["region_nombre", "cluster_nombre", "depto_nombre"],
            values=val_metric,
            color="indice_vulnerabilidad_ivst",
            color_continuous_scale="RdYlGn_r",
            hover_data={"indice_vulnerabilidad_ivst": ":.2f"},
        )
        title = f"Jerarquía Territorial Sunburst: {get_indicator_meta(val_metric)['titulo']}"
        subtitle = "Navegación interactiva: Región SEGEPLAN -> Clúster Socioeconómico -> Departamento (color por IVST)"
        summary = {"metrica": val_metric, "total": round(float(pdf[val_metric].sum()), 2)}

    else:
        raise ValueError(f"tipo de pastel '{chart_type}' no reconocido")

    _apply_standard_layout(fig, title, subtitle, height=580)
    if c_type != "jerarquia_territorial":
        fig.update_traces(textfont=dict(size=12))

    return _serialize_figure(fig, f"pastel_{c_type}", title, subtitle, "pie" if c_type != "jerarquia_territorial" else "sunburst", summary, output_format)


def build_cost_of_living_forecast_chart(output_format: str = "json") -> Union[Dict[str, Any], str]:
    # serie temporal observada de canasta basica + regresion lineal y proyeccion a 12 meses
    basket_path = ECONOMY_DIR / "canasta_basica_mensual.parquet"
    if not basket_path.exists():
        raise FileNotFoundError(f"no se encontro archivo de canasta basica en: {basket_path}")

    df_basket = pl.read_parquet(basket_path).filter(pl.col("tipo_canasta") == "CBA").to_pandas()
    df_basket["mes_continuo"] = (df_basket["anio"] - 2024) * 12 + df_basket["mes"]

    fig = go.Figure()
    summary_stats = {}

    palette = {"Urbana": "#38bdf8", "Rural": "#10b981"}
    for domain in ["Urbana", "Rural"]:
        sub = df_basket[df_basket["dominio"] == domain].sort_values("mes_continuo")
        x = sub["mes_continuo"].values
        y = sub["costo_mensual_percapita"].values
        dates = pd.to_datetime(sub["anio"].astype(str) + "-" + sub["mes"].astype(str).str.zfill(2) + "-01")

        # serie historica observada
        fig.add_trace(go.Scatter(
            x=dates, y=y, mode="lines+markers",
            name=f"CBA {domain} Observada",
            line=dict(color=palette[domain], width=3),
            marker=dict(size=6),
        ))

        # tendencia ols y proyeccion 12 meses
        slope, intercept, r_val, _, _ = stats.linregress(x, y)
        future_x = np.arange(x[-1], x[-1] + 13)
        future_y = intercept + slope * future_x
        last_date = dates.iloc[-1]
        future_dates = pd.date_range(start=last_date, periods=13, freq="MS")

        fig.add_trace(go.Scatter(
            x=future_dates, y=future_y, mode="lines",
            name=f"Proyección {domain} (R²={r_val**2:.3f})",
            line=dict(color=palette[domain], width=2.5, dash="dash"),
        ))
        summary_stats[domain] = {
            "actual_gtq": round(float(y[-1]), 2),
            "proyeccion_12m_gtq": round(float(future_y[-1]), 2),
            "r2": round(float(r_val ** 2), 4),
        }

    title = "Evolución Mensual y Proyección Econométrica de la CBA Urbana vs Rural"
    subtitle = "Serie observada INE (2024–2026) y proyección lineal MCO a 12 meses por persona"
    _apply_standard_layout(fig, title, subtitle, height=540)
    fig.update_layout(xaxis_title="Mes", yaxis_title="Costo Mensual Per Cápita (GTQ)")

    return _serialize_figure(fig, "tendencia_cba_pronostico", title, subtitle, "line_forecast", summary_stats, output_format)


def build_ipc_trends_chart(view: str = "regiones", output_format: str = "json") -> Union[Dict[str, Any], str]:
    # evolucion de precios al consumidor por region, divisiones de gasto o poder adquisitivo
    v_mode = view.lower().strip()
    if v_mode == "regiones":
        df = pl.read_parquet(ECONOMY_DIR / "ipc_regiones.parquet").to_pandas()
        df["fecha"] = pd.to_datetime(df["anio"].astype(str) + "-" + df["mes"].astype(str).str.zfill(2) + "-01")
        fig = px.line(
            df.sort_values("fecha"),
            x="fecha", y="variacion_interanual_pct", color="region_nombre", markers=True,
            labels={"fecha": "Mes (2024)", "variacion_interanual_pct": "Inflación Interanual (%)", "region_nombre": "Región SEGEPLAN"},
        )
        title = "Inflación Interanual del IPC por Región Socioeconómica (2024)"
        subtitle = "Base Diciembre 2023 = 100 | Disparidad territorial entre Región Norte y Metropolitana"
    elif v_mode == "divisiones":
        df = pl.read_parquet(ECONOMY_DIR / "ipc_divisiones_gasto.parquet").to_pandas()
        df["fecha"] = pd.to_datetime(df["anio"].astype(str) + "-" + df["mes"].astype(str).str.zfill(2) + "-01")
        fig = px.line(
            df.sort_values("fecha"),
            x="fecha", y="variacion_interanual_pct", color="division_gasto", markers=True,
            labels={"fecha": "Mes (2024)", "variacion_interanual_pct": "Variación Interanual (%)", "division_gasto": "División CCIF"},
        )
        title = "Evolución del IPC por las 13 Divisiones de Gasto (CCIF, 2024)"
        subtitle = "Presión inflacionaria diferencial en alimentos, vivienda, transporte y salud"
    elif v_mode == "poder_adquisitivo":
        df = pl.read_parquet(ECONOMY_DIR / "ipc_poder_adquisitivo.parquet").to_pandas()
        df["fecha"] = pd.to_datetime(df["anio"].astype(str) + "-" + df["mes"].astype(str).str.zfill(2) + "-01")
        df["perdida_centavos"] = (df["perdida_poder_adquisitivo"] * 100.0).round(2)
        fig = px.area(
            df.sort_values("fecha"),
            x="fecha", y="perdida_centavos", markers=True,
            labels={"fecha": "Mes (2024)", "perdida_centavos": "Pérdida Acumulada (Centavos por Q1.00)"},
        )
        fig.update_traces(line_color="#ef4444", fillcolor="rgba(239, 68, 68, 0.25)")
        title = "Pérdida Acumulada del Poder Adquisitivo del Quetzal (2024)"
        subtitle = "Erosión monetaria acumulada por cada Q 1.00 frente a la base Diciembre 2023"
    else:
        raise ValueError(f"vista ipc '{view}' no valida")

    _apply_standard_layout(fig, title, subtitle, height=560)
    return _serialize_figure(fig, f"tendencia_ipc_{v_mode}", title, subtitle, "line", {"vista": v_mode}, output_format)


def build_demographic_growth_lines_chart(top_n: int = 8, output_format: str = "json") -> Union[Dict[str, Any], str]:
    # lineas historicas y proyectadas de poblacion departamental 2015-2030
    df_pop = pl.read_parquet(DEMOGRAPHY_DIR / "poblacion_proyectada_departamental.parquet").to_pandas()
    df_growth = pl.read_parquet(ANALYSIS_DIR / "proyecciones_demograficas.parquet").to_pandas()
    top_deptos = df_growth.sort_values("tasa_anual_crecimiento_geometrico_pct", ascending=False).head(top_n)["depto_nombre"].tolist()

    sub = df_pop[df_pop["depto_nombre"].isin(top_deptos)].sort_values(["depto_nombre", "anio"])
    fig = px.line(
        sub,
        x="anio", y="poblacion_total", color="depto_nombre", markers=True,
        labels={"anio": "Año", "poblacion_total": "Población Total Proyectada", "depto_nombre": "Departamento"},
    )
    title = f"Curvas de Expansión Demográfica 2015–2030 (Top {top_n} Mayor Crecimiento)"
    subtitle = "Crecimiento poblacional proyectado INE (Huehuetenango +1.67% y Alta Verapaz +1.61% anual)"
    _apply_standard_layout(fig, title, subtitle, height=540)
    return _serialize_figure(fig, "tendencia_demografica_2030", title, subtitle, "line", {"departamentos": top_deptos}, output_format)


def build_correlation_heatmap_chart(method: str = "pearson", output_format: str = "json") -> Union[Dict[str, Any], str]:
    # mapa de calor simetrico anotado de correlaciones pearson o spearman
    pdf = load_enriched_department_df()
    cols = [
        "tasa_retorno_migratorio_por_10k",
        "indice_vulnerabilidad_ivst",
        "razon_dependencia_demografica",
        "tasa_natalidad_por_1000",
        "tasa_mortalidad_por_1000",
        "tasa_matricula_superior_por_10k",
        "pct_mujeres_superior",
        "tasa_necropsias_por_100k",
        "tasa_victimas_viales_por_100k",
        "tasa_mortalidad_vial_por_100k",
        "inflacion_regional_interanual",
    ]
    short_labels = [
        "Retorno Migr.",
        "Índice IVST",
        "Dependencia",
        "Natalidad",
        "Mortalidad",
        "Ed. Superior",
        "% Muj. Univ.",
        "Necropsias",
        "Víct. Viales",
        "Mort. Vial",
        "Inflación",
    ]

    m_type = "spearman" if method.lower() == "spearman" else "pearson"
    corr_mat = pdf[cols].corr(method=m_type).round(2)

    fig = px.imshow(
        corr_mat.values,
        x=short_labels,
        y=short_labels,
        zmin=-1.0,
        zmax=1.0,
        color_continuous_scale="RdBu_r",
        text_auto=".2f",
        aspect="auto",
    )
    title = f"Matriz de Correlaciones Bivariadas ({m_type.capitalize()})"
    subtitle = "Coeficientes entre indicadores departamentales (azul = asociación negativa, rojo = positiva)"
    _apply_standard_layout(fig, title, subtitle, height=620)
    fig.update_xaxes(side="bottom", tickangle=-35)

    return _serialize_figure(fig, f"heatmap_correlacion_{m_type}", title, subtitle, "heatmap", {"metodo": m_type}, output_format)


def build_outliers_boxplot_chart(output_format: str = "json") -> Union[Dict[str, Any], str]:
    # diagramas de caja estandarizados z-score mostrando todos los valores atipicos territoriales
    pdf = load_enriched_department_df()
    metrics = [
        ("tasa_victimas_viales_por_100k", "Víctimas Viales"),
        ("tasa_mortalidad_vial_por_100k", "Mortalidad Vial"),
        ("tasa_necropsias_por_100k", "Necropsias"),
        ("tasa_retorno_migratorio_por_10k", "Retorno Migratorio"),
        ("tasa_matricula_superior_por_10k", "Matrícula Superior"),
        ("razon_dependencia_demografica", "Dependencia Demog."),
        ("tasa_natalidad_por_1000", "Natalidad"),
        ("inflacion_regional_interanual", "Inflación Reg."),
    ]

    rows_long = []
    for col, label in metrics:
        s = pdf[col].astype(float)
        std = s.std(ddof=1)
        z_vals = (s - s.mean()) / std if std > 0 else s * 0.0
        for idx, z in enumerate(z_vals):
            rows_long.append({
                "Indicador": label,
                "Z-Score": round(float(z), 2),
                "Departamento": str(pdf.iloc[idx]["depto_nombre"]),
                "Valor Real": round(float(s.iloc[idx]), 2),
                "Es Outlier (|Z|>=2)": abs(z) >= 2.0,
            })

    long_df = pd.DataFrame(rows_long)
    fig = px.box(
        long_df,
        x="Indicador",
        y="Z-Score",
        points="all",
        hover_name="Departamento",
        hover_data={"Valor Real": True, "Z-Score": True},
        color="Indicador",
    )
    fig.add_hline(y=2.0, line_dash="dash", line_color="#ef4444", annotation_text="Umbral Outlier (+2σ)")
    fig.add_hline(y=-2.0, line_dash="dash", line_color="#ef4444", annotation_text="Umbral Outlier (-2σ)")

    title = "Detección Multivariada de Valores Atípicos Territoriales (Z-Score)"
    subtitle = "Escuintla (+2.83σ vial), Guatemala (+2.75σ univ. / -2.08σ migr.), Sacatepéquez (-2.41σ migr.) y Verapaces (+2.03σ inflación)"
    _apply_standard_layout(fig, title, subtitle, height=580)
    fig.update_layout(showlegend=False)

    return _serialize_figure(fig, "boxplot_outliers", title, subtitle, "boxplot", {"umbrales": "±2.0 sigma"}, output_format)


def build_department_radar_chart(
    depto_codigo: int = 13,
    compare_code: Optional[int] = 1,
    output_format: str = "json",
) -> Union[Dict[str, Any], str]:
    # grafica radar comparativa multidimensional normalizada 0-100 entre departamentos o media nacional
    pdf = load_enriched_department_df()
    dims = [
        ("tasa_retorno_migratorio_por_10k", "Retorno Migratorio"),
        ("razon_dependencia_demografica", "Dependencia Demog."),
        ("tasa_necropsias_por_100k", "Violencia Forense"),
        ("tasa_victimas_viales_por_100k", "Siniestralidad Vial"),
        ("tasa_matricula_superior_por_10k", "Educación Superior"),
        ("inflacion_regional_interanual", "Inflación Regional"),
    ]

    # normalizar todas las dimensiones a escala 0-100 para comparacion visual uniforme
    norm_df = pdf.copy()
    for col, _ in dims:
        c_min, c_max = pdf[col].min(), pdf[col].max()
        norm_df[col] = ((pdf[col] - c_min) / (c_max - c_min) * 100.0) if c_max > c_min else 50.0

    row_a = norm_df[norm_df["depto_codigo"] == depto_codigo]
    if len(row_a) == 0:
        raise ValueError(f"departamento {depto_codigo} no encontrado")
    row_a = row_a.iloc[0]

    categories = [label for _, label in dims] + [dims[0][1]]
    vals_a = [round(float(row_a[c]), 1) for c, _ in dims]
    vals_a.append(vals_a[0])

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=vals_a, theta=categories, fill="toself",
        name=str(row_a["depto_nombre"]), line_color="#f43f5e", fillcolor="rgba(244, 63, 94, 0.30)",
    ))

    comp_name = "Media Nacional"
    if compare_code is not None:
        row_b = norm_df[norm_df["depto_codigo"] == compare_code]
        if len(row_b) > 0:
            row_b = row_b.iloc[0]
            comp_name = str(row_b["depto_nombre"])
            vals_b = [round(float(row_b[c]), 1) for c, _ in dims]
            vals_b.append(vals_b[0])
        else:
            vals_b = [round(float(norm_df[c].mean()), 1) for c, _ in dims]
            vals_b.append(vals_b[0])
    else:
        vals_b = [round(float(norm_df[c].mean()), 1) for c, _ in dims]
        vals_b.append(vals_b[0])

    fig.add_trace(go.Scatterpolar(
        r=vals_b, theta=categories, fill="toself",
        name=comp_name, line_color="#38bdf8", fillcolor="rgba(56, 189, 248, 0.25)",
    ))

    title = f"Perfil Radar Multidimensional: {row_a['depto_nombre']} vs {comp_name}"
    subtitle = "Escala normalizada relativa (0 = mínimo nacional, 100 = máximo nacional)"
    _apply_standard_layout(fig, title, subtitle, height=560)
    fig.update_layout(polar=dict(bgcolor="#0f172a", radialaxis=dict(visible=True, range=[0, 100], gridcolor="#334155")))

    return _serialize_figure(
        fig,
        f"radar_{depto_codigo}",
        title,
        subtitle,
        "radar",
        {"principal": str(row_a["depto_nombre"]), "comparacion": comp_name},
        output_format,
    )


def prebuild_all_visualizations(include_blender: bool = True, force_refresh: bool = False) -> Dict[str, Any]:
    # pregenerar todas las graficas 2d, 3d, mapas, modelos y renders blender en disco
    from src.process.process import create_plotly_choropleth, build_guatemala_sidebar_html, export_folium_map
    from src.process.relief_3d import (
        build_deckgl_3d_relief_html,
        build_guatemala_relief_scene,
        render_guatemala_with_blender,
    )

    jobs: List[Tuple[str, Any]] = [
        ("3d_trayectoria_demografica_region_nombre", lambda output_format: build_3d_demographic_trajectory_chart("region_nombre", output_format)),
        ("3d_clusters_pca", lambda output_format: build_3d_pca_clusters_chart(output_format)),
        (
            "3d_riesgo_tasa_retorno_migratorio_por_10k_tasa_matricula_superior_por_10k_tasa_necropsias_por_100k_nivel_vulnerabilidad_poblacion_total",
            lambda output_format: build_3d_multidimensional_scatter_chart(output_format=output_format),
        ),
        ("3d_trayectoria_costo_vida", lambda output_format: build_3d_cost_of_living_trajectory_chart(output_format)),
        ("barras_estructura_demografica", lambda output_format: build_demographic_structure_stacked_bar_chart(output_format)),
        ("barras_composicion_retornados_12", lambda output_format: build_returnees_composition_bar_chart(12, output_format)),
        ("barras_muni_tasa_necropsias_por_100k_all_20", lambda output_format: build_municipal_ranking_bar_chart("tasa_necropsias_por_100k", None, 20, output_format)),
        ("tendencia_costo_vida", lambda output_format: build_cost_of_living_forecast_chart(output_format)),
        ("tendencia_ipc_regiones", lambda output_format: build_ipc_trends_chart("regiones", output_format)),
        ("tendencia_ipc_divisiones", lambda output_format: build_ipc_trends_chart("divisiones", output_format)),
        ("tendencia_ipc_poder_adquisitivo", lambda output_format: build_ipc_trends_chart("poder_adquisitivo", output_format)),
        ("tendencia_demografica_8", lambda output_format: build_demographic_growth_lines_chart(8, output_format)),
        ("heatmap_pearson", lambda output_format: build_correlation_heatmap_chart("pearson", output_format)),
        ("heatmap_spearman", lambda output_format: build_correlation_heatmap_chart("spearman", output_format)),
        ("boxplot_outliers", lambda output_format: build_outliers_boxplot_chart(output_format)),
        ("radar_13_1", lambda output_format: build_department_radar_chart(13, 1, output_format)),
    ]

    for ind in [
        "indice_vulnerabilidad_ivst",
        "tasa_retorno_migratorio_por_10k",
        "tasa_necropsias_por_100k",
        "tasa_victimas_viales_por_100k",
        "tasa_matricula_superior_por_10k",
    ]:
        jobs.append((
            f"barras_depto_{ind}_22_desc_h_nivel_vulnerabilidad",
            lambda output_format, i=ind: build_department_ranking_bar_chart(i, 22, "desc", "h", "nivel_vulnerabilidad", output_format),
        ))

    for ptype in [
        "clusters", "retornados_edad", "retornados_genero",
        "educacion_genero", "victimas_viales", "estructura_etaria", "jerarquia_territorial",
    ]:
        jobs.append((
            f"pastel_{ptype}_all_poblacion_total",
            lambda output_format, pt=ptype: build_pie_distribution_chart(pt, None, "poblacion_total", output_format),
        ))

    charts_built = 0
    for key, fn in jobs:
        for fmt in ("html", "json"):
            get_or_build_chart(key, fmt, fn, force_refresh=force_refresh)
            charts_built += 1

    # pregenerar mapas 2d, relieve 3d deck.gl, modelo glb y render blender para indicadores principales
    maps_dir = DATA_PROCESSED / "mapas"
    models_dir = DATA_PROCESSED / "modelos_3d"
    renders_dir = DATA_PROCESSED / "renders_blender"
    for d in [maps_dir, models_dir, renders_dir]:
        d.mkdir(parents=True, exist_ok=True)

    featured_indicators = ["indice_vulnerabilidad_ivst", "tasa_retorno_migratorio_por_10k", "tasa_necropsias_por_100k"]
    maps_built = 0
    blender_built = 0

    for ind in featured_indicators:
        merged_gdf, meta = load_enriched_geo_dataframe(ind)

        # mapa folium
        folium_out = maps_dir / f"mapa_folium_{ind}.html"
        if force_refresh or not folium_out.exists():
            export_folium_map(
                merged_gdf=merged_gdf,
                output_html_path=folium_out,
                value_col=ind,
                colormap="YlOrRd",
                tooltip_cols=["nombre", ind],
                tiles="Esri.WorldGrayCanvas",
                topic_title=meta["titulo"],
            )
            maps_built += 1

        # mapa plotly 2d
        plotly_html_out = maps_dir / f"mapa_plotly_{ind}.html"
        if force_refresh or not plotly_html_out.exists():
            fig = create_plotly_choropleth(merged_gdf, "cod", ind, "nombre", topic_title=meta["titulo"])
            markup = fig.to_html(include_plotlyjs="cdn")
            sidebar = build_guatemala_sidebar_html(merged_gdf, value_col=ind, name_col="nombre", topic_title=meta["titulo"])
            if sidebar and "</body>" in markup:
                markup = markup.replace("</body>", f"{sidebar}</body>")
            plotly_html_out.write_text(markup, encoding="utf-8")
            maps_built += 1

        # mapa relieve 3d deck.gl
        deck_out = maps_dir / f"mapa_3d_{ind}_multicolor.html"
        if force_refresh or not deck_out.exists():
            deck_html = build_deckgl_3d_relief_html(
                merged_gdf, value_col=ind, name_col="nombre", code_col="cod",
                topic_title=meta["titulo"], color_mode="multicolor", max_elevation_m=65000.0,
            )
            deck_out.write_text(deck_html, encoding="utf-8")
            maps_built += 1

        # escena 3d glb
        glb_out = models_dir / f"modelo_3d_{ind}_multicolor.glb"
        if force_refresh or not glb_out.exists():
            scene = build_guatemala_relief_scene(
                merged_gdf, value_col=ind, code_col="cod", name_col="nombre",
                target_width_mm=150.0, base_mm=0.6, forma_base="silueta",
                max_relief_mm=60.0, add_camera=True, color_mode="multicolor",
            )
            scene.export(str(glb_out))

        # render blender solo para los dos indicadores estrella para agilizar tiempo
        if include_blender and ind in ["indice_vulnerabilidad_ivst", "tasa_retorno_migratorio_por_10k"]:
            png_out = renders_dir / f"render_blender_{ind}_multicolor_1280x720.png"
            if force_refresh or not png_out.exists():
                try:
                    render_guatemala_with_blender(glb_out, png_out, width=1280, height=720, color_mode="multicolor")
                    blender_built += 1
                except Exception:
                    pass

    return {
        "graficas_en_cache": charts_built,
        "mapas_generados": maps_built,
        "renders_blender_generados": blender_built,
        "directorio_cache": str(VISUALIZATIONS_DIR),
    }
