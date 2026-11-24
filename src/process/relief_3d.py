from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Union

from src.core.config import PROCESSED_DATA_DIR

# paleta de 22 colores especificos para los departamentos de guatemala
DEPT_COLORS_RGB: Dict[str, tuple[int, int, int]] = {
    "01": (59, 130, 246),   # guatemala: azul real
    "02": (16, 185, 129),   # el progreso: esmeralda
    "03": (245, 158, 11),   # sacatepequez: ambar
    "04": (239, 68, 68),    # chimaltenango: rojo coral
    "05": (139, 92, 246),   # escuintla: purpura
    "06": (236, 72, 153),   # santa rosa: rosa intenso
    "07": (14, 165, 233),   # solola: celeste lago
    "08": (249, 115, 22),   # totonicapan: naranja
    "09": (168, 85, 247),   # quetzaltenango: violeta
    "10": (34, 197, 94),    # suchitepequez: verde
    "11": (234, 179, 8),    # retalhuleu: amarillo dorado
    "12": (6, 182, 212),    # san marcos: turquesa
    "13": (225, 29, 72),    # huehuetenango: carmin
    "14": (217, 70, 239),   # quiche: fucsia
    "15": (20, 184, 166),   # baja verapaz: teal
    "16": (132, 204, 22),   # alta verapaz: lima
    "17": (79, 70, 229),    # peten: indigo
    "18": (2, 132, 199),    # izabal: azul caribe
    "19": (194, 65, 12),    # zacapa: ocre
    "20": (180, 83, 9),     # chiquimula: bronce
    "21": (157, 23, 77),    # jalapa: magenta
    "22": (101, 163, 13),   # jutiapa: oliva
}

DEPT_COLORS_HEX: Dict[str, str] = {
    "01": "#3b82f6", "02": "#10b981", "03": "#f59e0b", "04": "#ef4444",
    "05": "#8b5cf6", "06": "#ec4899", "07": "#0ea5e9", "08": "#f97316",
    "09": "#a855f7", "10": "#22c55e", "11": "#eab308", "12": "#06b6d4",
    "13": "#e11d48", "14": "#d946ef", "15": "#14b8a6", "16": "#84cc16",
    "17": "#4f46e5", "18": "#0284c7", "19": "#c2410c", "20": "#b45309",
    "21": "#9d174d", "22": "#65a30d"
}


def _require_trimesh() -> Any:
    """Importar trimesh de forma diferida con mensaje informativo."""
    try:
        import trimesh
        return trimesh
    except ImportError as exc:
        raise ImportError(
            "se requiere trimesh y shapely para modelos 3d. "
            "instale con: pip install trimesh shapely"
        ) from exc


def build_deckgl_3d_relief_html(
    merged_gdf: Any,
    value_col: str = "valor",
    name_col: str = "nombre",
    code_col: str = "cod",
    topic_title: Optional[str] = None,
    color_mode: str = "multicolor",
    max_elevation_m: float = 60000.0,
    center_lat: float = 15.78,
    center_lon: float = -90.23,
    zoom: float = 6.8,
    pitch: float = 56.0,
    bearing: float = -20.0
) -> str:
    """Construir mapa interactivo 3d con relieve extruido en deck.gl con multiples perspectivas y colores."""
    max_val = float(merged_gdf[value_col].max()) if hasattr(merged_gdf, "__len__") and len(merged_gdf) > 0 else 1.0
    if max_val <= 0:
        max_val = 1.0

    # obtener representacion geojson directamente como diccionario
    raw_interface = getattr(merged_gdf, "__geo_interface__", None)
    if isinstance(raw_interface, str):
        geo_data = json.loads(raw_interface)
    elif isinstance(raw_interface, dict):
        geo_data = json.loads(json.dumps(raw_interface))
    else:
        geo_data = {"type": "FeatureCollection", "features": []}

    # calcular elevacion, normalizacion y colores especificos para cada departamento
    for feat in geo_data.get("features", []):
        props = feat.get("properties", {})
        code = str(props.get(code_col, "")).zfill(2)
        val = float(props.get(value_col) or 0.0)
        props["elevation_m"] = (val / max_val) * float(max_elevation_m)
        props["norm"] = val / max_val
        props["nombre_tooltip"] = props.get(name_col, "Dpto")
        props["valor_tooltip"] = val
        props["color_rgb"] = list(DEPT_COLORS_RGB.get(code, (56, 189, 248)))
        props["color_hex"] = DEPT_COLORS_HEX.get(code, "#38bdf8")

    geo_json_str = json.dumps(geo_data).replace("</", "<\\/")
    display_title = topic_title or f"Datos de {value_col.capitalize()}"

    # ordenar datos para el ranking lateral
    sorted_df = merged_gdf.sort_values(by=value_col, ascending=False) if hasattr(merged_gdf, "sort_values") else merged_gdf
    total_val = int(merged_gdf[value_col].sum()) if hasattr(merged_gdf, "__getitem__") else 0
    avg_val = int(merged_gdf[value_col].mean()) if hasattr(merged_gdf, "__getitem__") else 0
    max_row = sorted_df.iloc[0] if len(sorted_df) > 0 else {}
    min_row = sorted_df.iloc[-1] if len(sorted_df) > 0 else {}

    items_html = ""
    for idx, (_, row) in enumerate(sorted_df.iterrows(), start=1):
        pct = (float(row.get(value_col, 0)) / max_val) * 100
        val_f = f"{int(row.get(value_col, 0)):,}"
        c_code = str(row.get(code_col, "")).zfill(2)
        c_hex = DEPT_COLORS_HEX.get(c_code, "#38bdf8")
        items_html += f"""
        <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 8px; border-bottom:1px solid #1e293b; font-size:12px;">
          <div style="flex:1;">
            <div style="display:flex; align-items:center; gap:6px;">
              <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:{c_hex}; flex-shrink:0;"></span>
              <span style="font-weight:600; color:#f8fafc;">#{idx} {row.get(name_col, 'Dpto')}</span>
            </div>
            <div style="background:#334155; border-radius:3px; height:4px; width:100%; margin-top:4px; overflow:hidden;">
              <div style="background:linear-gradient(90deg, {c_hex}, #ef4444); height:100%; width:{pct:.1f}%;"></div>
            </div>
          </div>
          <div style="margin-left:12px; font-weight:700; color:#38bdf8; text-align:right;">
            {val_f}
          </div>
        </div>
        """

    html_template = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<title>Mapa 3D con Relieve y Perspectivas - Guatemala</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<script src="https://unpkg.com/deck.gl@9/dist.min.js"></script>
<style>
  body {{ margin:0; background:#080d1a; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif; overflow:hidden; }}
  #deckgl-container {{ width:100vw; height:100vh; position:absolute; top:0; left:0; }}
  
  /* barra de perspectivas superior izquierda */
  #toolbar-perspectivas {{
    position:fixed; top:16px; left:16px; z-index:999;
    background:rgba(15,23,42,0.92); backdrop-filter:blur(12px);
    border:1px solid #334155; border-radius:12px; padding:8px 12px;
    box-shadow:0 12px 28px -5px rgba(0,0,0,0.5); display:flex; flex-direction:column; gap:6px;
  }}
  .tb-title {{ font-size:10px; font-weight:800; color:#94a3b8; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:2px; }}
  .btn-row {{ display:flex; gap:5px; flex-wrap:wrap; }}
  .btn-view {{
    background:#1e293b; border:1px solid #334155; color:#f8fafc; border-radius:6px;
    cursor:pointer; font-size:11px; font-weight:700; padding:6px 10px;
    display:inline-flex; align-items:center; gap:4px; transition:all 0.2s;
  }}
  .btn-view:hover {{ background:#0284c7; border-color:#38bdf8; }}
  .btn-view.active {{ background:#0284c7; border-color:#38bdf8; box-shadow:0 0 10px rgba(56,189,248,0.4); }}
  .btn-highlight {{ background:#0284c7; border-color:#38bdf8; }}
  
  /* panel lateral derecho */
  #gt-3d-sidebar {{
    position:fixed; top:16px; right:16px; width:340px; max-height:calc(100vh - 32px);
    z-index:999; background:rgba(15,23,42,0.94); backdrop-filter:blur(14px);
    border-radius:14px; box-shadow:0 12px 30px -5px rgba(0,0,0,0.5);
    color:#f8fafc; display:flex; flex-direction:column; overflow:hidden; border:1px solid #334155;
  }}
  .kpi-box {{ background:#1e293b; padding:8px 10px; border-radius:8px; border:1px solid #334155; }}
  .btn-mode {{
    flex:1; background:#1e293b; border:1px solid #334155; color:#cbd5e1; border-radius:6px;
    cursor:pointer; font-size:10px; font-weight:700; padding:6px 4px; text-align:center; transition:all 0.2s;
  }}
  .btn-mode:hover {{ background:#334155; color:#fff; }}
  .btn-mode.active {{ background:#0284c7; border-color:#38bdf8; color:#fff; font-weight:800; }}
  .btn-scale {{
    background:#1e293b; border:1px solid #334155; color:#cbd5e1; border-radius:4px;
    cursor:pointer; font-size:10px; font-weight:700; padding:3px 7px;
  }}
  .btn-scale:hover {{ background:#0284c7; color:#fff; }}
  .btn-scale.active {{ background:#0284c7; color:#fff; border-color:#38bdf8; }}
  
  /* pildora inferior con instrucciones de navegacion */
  #instructions-pill {{
    position:fixed; bottom:16px; left:50%; transform:translateX(-50%); z-index:998;
    background:rgba(15,23,42,0.88); backdrop-filter:blur(8px);
    border:1px solid #334155; border-radius:30px; padding:7px 18px;
    color:#cbd5e1; font-size:11px; box-shadow:0 6px 20px rgba(0,0,0,0.4);
    display:flex; align-items:center; gap:12px; pointer-events:none;
  }}
</style>
</head>
<body>
<div id="deckgl-container"></div>

<!-- barra flotante de perspectivas -->
<div id="toolbar-perspectivas">
  <div class="tb-title">🔭 Perspectivas y Controles 3D</div>
  <div class="btn-row">
    <button class="btn-view" onclick="setPerspective('iso')" title="Vista Isometrica 3D">🔭 3D Iso</button>
    <button class="btn-view" onclick="setPerspective('cenital')" title="Vista Superior 2D">⬆️ Cenital</button>
    <button class="btn-view" onclick="setPerspective('frontal')" title="Vista Frontal Sur">📐 Frontal</button>
    <button class="btn-view" onclick="setPerspective('lateral')" title="Vista Lateral Perfil">🌄 Lateral</button>
    <button class="btn-view" id="btn-rotate" onclick="toggleAutoRotate()" title="Rotacion continua 360 grados">🔄 Girar 360°</button>
    <button class="btn-view btn-highlight" onclick="centrarMapaGuatemala()" title="Re-centrar mapa en Guatemala">🎯 Centrar</button>
  </div>
</div>

<!-- pildora de ayuda de controles -->
<div id="instructions-pill">
  <span>🖱️ <b>Clic derecho o Ctrl + clic:</b> Rotar 360° en cualquier perspectiva</span>
  <span>•</span>
  <span><b>Clic izquierdo:</b> Desplazar</span>
  <span>•</span>
  <span><b>Rueda:</b> Zoom</span>
</div>

<!-- panel lateral de estadisticas y opciones -->
<div id="gt-3d-sidebar">
  <div style="padding:12px 14px; background:linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%); border-bottom:1px solid #334155; display:flex; justify-content:space-between; align-items:center;">
    <div style="display:flex; align-items:center; gap:8px;">
      <span style="font-size:22px;">🇬🇹</span>
      <div>
        <h3 style="margin:0; font-size:13px; font-weight:800;">Estadísticas de Guatemala</h3>
        <p style="margin:1px 0 0 0; font-size:10px; opacity:0.8;">Instituto Nacional de Estadística (INE)</p>
        <div style="font-size:11px; font-weight:700; color:#38bdf8; margin-top:3px; background:rgba(56,189,248,0.15); padding:2px 7px; border-radius:4px; display:inline-block;">
          📊 {display_title}
        </div>
      </div>
    </div>
    <button onclick="toggleSidebar3D(this)" style="background:rgba(255,255,255,0.15); border:none; color:white; border-radius:6px; cursor:pointer; font-size:14px; font-weight:bold; width:26px; height:26px;">—</button>
  </div>

  <div id="sidebar-collapsible" style="display:flex; flex-direction:column; overflow:hidden;">
    <!-- selector de modo de color del relieve -->
    <div style="padding:10px 12px; background:#0b1329; border-bottom:1px solid #1e293b;">
      <div style="font-size:10px; font-weight:800; color:#94a3b8; text-transform:uppercase; margin-bottom:6px;">
        🎨 Estilo y Diferenciación de Relieve
      </div>
      <div style="display:flex; gap:5px;">
        <button id="btn-col-multicolor" class="btn-mode active" onclick="setColorMode('multicolor')" title="Asignar un color distintivo a cada departamento">🎨 22 Colores</button>
        <button id="btn-col-negro" class="btn-mode" onclick="setColorMode('negro')" title="Relieve negro mate con aristas luminosas contrastadas">⬛ Relieve Negro</button>
        <button id="btn-col-calor" class="btn-mode" onclick="setColorMode('calor')" title="Gradiente termico proporcional al dato">🔥 Gradiente</button>
      </div>
      <div style="margin-top:10px; display:flex; align-items:center; justify-content:space-between; font-size:11px; color:#cbd5e1;">
        <span>Escala de Relieve: <b id="lbl-scale" style="color:#38bdf8;">1.0x</b></span>
        <div style="display:flex; gap:4px;">
          <button class="btn-scale" onclick="adjustScale(0.5)">0.5x</button>
          <button class="btn-scale active" id="scale-1" onclick="adjustScale(1.0)">1.0x</button>
          <button class="btn-scale" onclick="adjustScale(1.6)">1.6x</button>
          <button class="btn-scale" onclick="adjustScale(2.5)">2.5x</button>
        </div>
      </div>
    </div>

    <!-- kpis nacionales -->
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; padding:10px; background:#0f172a; border-bottom:1px solid #1e293b;">
      <div class="kpi-box">
        <div style="font-size:10px; color:#94a3b8; font-weight:700; text-transform:uppercase;">Total Nacional</div>
        <div style="font-size:17px; font-weight:800; color:#38bdf8; margin-top:2px;">{total_val:,}</div>
      </div>
      <div class="kpi-box">
        <div style="font-size:10px; color:#94a3b8; font-weight:700; text-transform:uppercase;">Promedio Dpto</div>
        <div style="font-size:17px; font-weight:800; color:#38bdf8; margin-top:2px;">{avg_val:,}</div>
      </div>
      <div class="kpi-box" style="grid-column:span 2; font-size:11px;">
        <div style="display:flex; justify-content:space-between;">
          <span>🏆 <b>Mayor:</b> {max_row.get(name_col, '')} ({int(max_row.get(value_col, 0)):,})</span>
          <span style="color:#94a3b8;">📉 <b>Menor:</b> {min_row.get(name_col, '')} ({int(min_row.get(value_col, 0)):,})</span>
        </div>
      </div>
    </div>

    <div style="padding:8px 12px 4px; font-size:10px; font-weight:800; color:#94a3b8; text-transform:uppercase; letter-spacing:0.5px;">
      Desglose Departamental
    </div>
    <div style="overflow-y:auto; max-height:calc(100vh - 340px); padding:0 10px 10px;">
      {items_html}
    </div>
  </div>
</div>

<script>
const DATA = {geo_json_str};

let currentMode = '{color_mode}';
let currentScale = 1.0;
let isRotating = false;
let rotateRaf = null;

// paleta de calor para modo gradiente
function colorGradient(t) {{
  if (t < 0.25) return [56, 189, 248];
  if (t < 0.5) return [74, 222, 128];
  if (t < 0.75) return [250, 204, 21];
  return [239, 68, 68];
}}

function getDepartmentColor(feature) {{
  if (currentMode === 'negro') {{
    return [22, 24, 30, 255]; // negro carbon azabache mate
  }}
  if (currentMode === 'multicolor') {{
    return feature.properties.color_rgb || [56, 189, 248, 255];
  }}
  return colorGradient(feature.properties.norm || 0);
}}

function getDepartmentLineColor(feature) {{
  if (currentMode === 'negro') {{
    return [56, 189, 248, 255]; // aristas cian neon para maximo contraste
  }}
  return [10, 15, 26, 255]; // trazo oscuro nítido
}}

const initialView = {{
  latitude: {center_lat}, longitude: {center_lon},
  zoom: {zoom}, pitch: {pitch}, bearing: {bearing},
  maxPitch: 89, minPitch: 0
}};

const PERSPECTIVES = {{
  iso: {{ latitude: 15.65, longitude: -90.23, zoom: 6.9, pitch: 58, bearing: -22, maxPitch: 89, minPitch: 0 }},
  cenital: {{ latitude: 15.78, longitude: -90.23, zoom: 7.1, pitch: 0, bearing: 0, maxPitch: 89, minPitch: 0 }},
  frontal: {{ latitude: 15.15, longitude: -90.23, zoom: 6.9, pitch: 68, bearing: 0, maxPitch: 89, minPitch: 0 }},
  lateral: {{ latitude: 15.78, longitude: -89.70, zoom: 6.8, pitch: 64, bearing: -85, maxPitch: 89, minPitch: 0 }}
}};

const deckInstance = new deck.DeckGL({{
  container: 'deckgl-container',
  initialViewState: initialView,
  controller: {{
    dragRotate: true,
    dragPan: true,
    scrollZoom: true,
    doubleClickZoom: true,
    touchRotate: true,
    inertia: 250,
    keyboard: true
  }},
  layers: [buildLayer()],
  getTooltip: ({{object}}) => object && object.properties && ({{
    html: '<div style=\"font-size:13px; font-weight:800; color:#38bdf8;\">' + object.properties.nombre_tooltip + '</div>' +
          '<div><b>Valor:</b> ' + Number(object.properties.valor_tooltip).toLocaleString('es-GT') + '</div>' +
          '<div style=\"color:#94a3b8; font-size:11px;\"><b>Relieve:</b> ' + Math.round((object.properties.elevation_m * currentScale) / 1000) + ' km</div>',
    style: {{ backgroundColor: '#0f172a', color: '#fff', fontSize: '12px', borderRadius: '8px', padding: '10px', border: '1px solid #334155' }}
  }})
}});

window.deckInstance = deckInstance;

function buildLayer() {{
  return new deck.GeoJsonLayer({{
    id: 'gt-relieve-3d',
    data: DATA,
    extruded: true,
    filled: true,
    stroked: true,
    getPolygon: f => f.geometry.coordinates,
    getElevation: f => (f.properties.elevation_m || 0) * currentScale,
    getFillColor: f => getDepartmentColor(f),
    getLineColor: f => getDepartmentLineColor(f),
    lineWidthMinPixels: currentMode === 'negro' ? 2.5 : 1.8,
    pickable: true,
    autoHighlight: true,
    highlightColor: [255, 255, 255, 140],
    material: {{ ambient: 0.45, diffuse: 0.70, shininess: 45, specularColor: [80, 80, 80] }},
    updateTriggers: {{
      getFillColor: [currentMode],
      getLineColor: [currentMode],
      getElevation: [currentScale],
      lineWidthMinPixels: [currentMode]
    }}
  }});
}}

function setColorMode(mode) {{
  currentMode = mode;
  ['multicolor', 'negro', 'calor'].forEach(m => {{
    const el = document.getElementById('btn-col-' + m);
    if (el) el.classList.toggle('active', m === mode);
  }});
  deckInstance.setProps({{ layers: [buildLayer()] }});
}}

function adjustScale(factor) {{
  currentScale = factor;
  document.getElementById('lbl-scale').innerText = factor.toFixed(1) + 'x';
  document.querySelectorAll('.btn-scale').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  deckInstance.setProps({{ layers: [buildLayer()] }});
}}

function setPerspective(key) {{
  if (isRotating) toggleAutoRotate();
  const target = PERSPECTIVES[key] || PERSPECTIVES.iso;
  deckInstance.setProps({{
    initialViewState: {{
      ...target,
      transitionDuration: 1000,
      transitionInterpolator: new deck.FlyToInterpolator()
    }}
  }});
}}

function toggleAutoRotate() {{
  const btn = document.getElementById('btn-rotate');
  if (isRotating) {{
    isRotating = false;
    cancelAnimationFrame(rotateRaf);
    btn.innerText = '🔄 Girar 360°';
    btn.classList.remove('active');
  }} else {{
    isRotating = true;
    btn.innerText = '⏸️ Pausar Giro';
    btn.classList.add('active');
    function step() {{
      if (!isRotating) return;
      const cur = deckInstance.viewState || deckInstance.props.initialViewState;
      const nextBearing = ((cur.bearing || 0) + 0.35) % 360;
      deckInstance.setProps({{
        initialViewState: {{
          ...cur,
          bearing: nextBearing
        }}
      }});
      rotateRaf = requestAnimationFrame(step);
    }}
    rotateRaf = requestAnimationFrame(step);
  }}
}}

function centrarMapaGuatemala() {{
  if (isRotating) toggleAutoRotate();
  deckInstance.setProps({{
    initialViewState: {{
      ...initialView,
      transitionDuration: 1000,
      transitionInterpolator: new deck.FlyToInterpolator()
    }}
  }});
}}

function toggleSidebar3D(btn) {{
  const content = document.getElementById('sidebar-collapsible');
  if (content.style.display === 'none') {{
    content.style.display = 'flex';
    btn.innerText = '—';
  }} else {{
    content.style.display = 'none';
    btn.innerText = '+';
  }}
}}

// inicializar modo activo
setColorMode(currentMode);
</script>
</body>
</html>"""
    return html_template


def build_guatemala_relief_scene(
    merged_gdf: Any,
    value_col: str = "valor",
    code_col: str = "cod",
    name_col: str = "nombre",
    target_width_mm: float = 150.0,
    base_mm: float = 0.6,
    forma_base: str = "silueta",
    max_relief_mm: float = 60.0,
    min_relief_mm: float = 0.8,
    simplify_m: float = 10.0,
    add_camera: bool = True,
    color_mode: str = "multicolor"
) -> Any:
    """Construir escena 3d con departamentos separados, materiales PBR de color y base delgada de silueta."""
    trimesh = _require_trimesh()
    import numpy as np
    import shapely.affinity
    from shapely.ops import unary_union

    # reproyectar a metros usando crtm05 oficial de guatemala
    gdf_proj = merged_gdf.to_crs(6362)
    max_val = float(gdf_proj[value_col].max()) if len(gdf_proj) > 0 else 1.0
    if max_val <= 0:
        max_val = 1.0

    minx, miny, maxx, maxy = gdf_proj.total_bounds
    scale = target_width_mm / max(maxx - minx, 1.0)
    cx_m = (minx + maxx) / 2
    cy_m = (miny + maxy) / 2

    scene = trimesh.Scene()

    for idx, row in gdf_proj.iterrows():
        val = float(row.get(value_col, 0))
        relief = max(min_relief_mm, (val / max_val) * max_relief_mm)
        geom = row.geometry
        code = str(row.get(code_col, f"{idx+1}")).zfill(2)
        raw_name = str(row.get(name_col, f"Dpto_{code}")).replace(" ", "_")
        name_clean = "".join(c for c in raw_name if c.isalnum() or c in ["_", "-"])

        # determinar material pbr segun estilo
        if color_mode in ["black", "negro"]:
            pbr_color = [0.07, 0.07, 0.09, 1.0] # negro obsidiana mate
            metallic = 0.30
            roughness = 0.35
        elif color_mode == "multicolor":
            rgb = DEPT_COLORS_RGB.get(code, (56, 189, 248))
            pbr_color = [rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, 1.0]
            metallic = 0.08
            roughness = 0.38
        else: # calor / gradiente
            norm = min(max(val / max_val, 0.0), 1.0)
            pbr_color = [
                (56 + norm * (239 - 56)) / 255.0,
                (189 * (1.0 - norm * 0.7)) / 255.0,
                (248 * (1.0 - norm)) / 255.0,
                1.0
            ]
            metallic = 0.08
            roughness = 0.38

        polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        dept_meshes = []
        for poly in polys:
            poly_s = poly.simplify(simplify_m, preserve_topology=True)
            poly_t = shapely.affinity.translate(poly_s, xoff=-cx_m, yoff=-cy_m)
            poly_mm = shapely.affinity.scale(poly_t, xfact=scale, yfact=scale, origin=(0, 0))
            dept_meshes.append(trimesh.creation.extrude_polygon(poly_mm, height=relief))

        if dept_meshes:
            dept_solid = trimesh.util.concatenate(dept_meshes)
            dept_solid.visual.material = trimesh.visual.material.PBRMaterial(
                baseColorFactor=pbr_color,
                metallicFactor=metallic,
                roughnessFactor=roughness,
                name=f"Mat_{code}_{name_clean}"
            )
            node_key = f"depto_{code}_{name_clean}"
            scene.add_geometry(dept_solid, geom_name=node_key, node_name=node_key)

    # base de soporte estilizada
    if base_mm > 0.0 and forma_base != "ninguna":
        base_material = trimesh.visual.material.PBRMaterial(
            baseColorFactor=[0.04, 0.05, 0.07, 1.0], # negro grafito mate
            metallicFactor=0.05,
            roughnessFactor=0.75,
            name="Mat_Base_Soporte"
        )
        if forma_base == "silueta":
            # la base sigue la silueta exacta de guatemala sin desbordar
            union_geom = unary_union(gdf_proj.geometry)
            u_s = union_geom.simplify(simplify_m, preserve_topology=True)
            u_t = shapely.affinity.translate(u_s, xoff=-cx_m, yoff=-cy_m)
            u_mm = shapely.affinity.scale(u_t, xfact=scale, yfact=scale, origin=(0, 0))
            base_polys = u_mm.geoms if hasattr(u_mm, "geoms") else [u_mm]
            b_meshes = [trimesh.creation.extrude_polygon(p, height=base_mm) for p in base_polys]
            base_solid = trimesh.util.concatenate(b_meshes)
            base_solid.apply_translation([0, 0, -base_mm])
        else:
            # caja rectangular compacta
            base_w = (maxx - minx) * scale + 4
            base_h = (maxy - miny) * scale + 4
            base_solid = trimesh.creation.box(extents=[base_w, base_h, base_mm])
            base_solid.apply_translation([0, 0, -base_mm / 2])

        base_solid.visual.material = base_material
        scene.add_geometry(base_solid, geom_name="base_guatemala", node_name="base_guatemala")

    if add_camera:
        try:
            total_w = (maxx - minx) * scale
            total_h = (maxy - miny) * scale
            diag = float(np.linalg.norm([total_w, total_h, max_relief_mm]))
            scene.camera = trimesh.scene.camera.Camera(resolution=(1280, 720), fov=(42, 42))
            target = np.array([0, 0, max_relief_mm * 0.25])
            pos = target + np.array([0.45, -0.60, 0.85]) * (diag * 1.6)
            rot = trimesh.geometry.align_vectors([0, 0, -1], target - pos)
            t_mat = np.eye(4)
            t_mat[:3, :3] = rot
            t_mat[:3, 3] = pos
            scene.camera_transform = t_mat
        except Exception:
            pass

    return scene


def render_guatemala_with_blender(
    glb_path: Union[str, Path],
    output_png_path: Union[str, Path],
    width: int = 1280,
    height: int = 720,
    color_mode: str = "multicolor",
    script_path: Optional[Union[str, Path]] = None
) -> Path:
    """Renderizar modelo glb usando blender en modo headless local o mediante docker multiplataforma."""
    in_path = Path(glb_path).resolve()
    out_path = Path(output_png_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    blender_bin = shutil.which("blender")
    docker_bin = shutil.which("docker")

    # mapear modo de color estandarizado
    norm_color = "black" if color_mode in ["black", "negro"] else ("blue" if color_mode in ["blue", "azul"] else "multicolor")

    # ejecucion directa si blender esta instalado localmente
    if blender_bin:
        script = Path(script_path).resolve() if script_path else Path("scripts/blender_render_guatemala.py").resolve()
        cmd = [
            blender_bin,
            "-b",
            "--python", str(script),
            "--",
            "--input", str(in_path),
            "--output", str(out_path),
            "--width", str(width),
            "--height", str(height),
            "--color-mode", norm_color
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            raise RuntimeError(f"error en ejecucion de blender: {result.stderr or result.stdout}")
        if not out_path.exists():
            raise RuntimeError("blender finalizo pero no genero el archivo de imagen de salida")
        return out_path

    # fallback con docker para entornos windows, macos o servidores sin blender local
    if docker_bin:
        project_root = Path(__file__).resolve().parent.parent.parent
        cmd_docker = [
            docker_bin, "compose",
            "-f", str(project_root / "docker-compose.blender.yml"),
            "run", "--rm", "blender",
            "--input", str(in_path),
            "--output", str(out_path),
            "--width", str(width),
            "--height", str(height),
            "--color-mode", norm_color
        ]
        result = subprocess.run(cmd_docker, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"error en docker de blender: {result.stderr or result.stdout}")
        if not out_path.exists():
            raise RuntimeError("docker blender finalizo pero no genero el archivo de imagen")
        return out_path

    raise RuntimeError(
        "blender no esta instalado localmente ni docker se encuentra disponible. "
        "para renderizar modelos 3d instale blender o ejecute el contenedor con: "
        "docker compose -f docker-compose.blender.yml up"
    )
