from __future__ import annotations

import unicodedata
from typing import Any, Dict, List, Optional, Union


def strip_accents(text: str) -> str:
    """Remover acentos y caracteres diacriticos de un texto para comparacion robusta."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).upper().strip()


# catalogo oficial de los 22 departamentos de guatemala segun el ine
DEPARTAMENTOS_INE: Dict[int, Dict[str, Any]] = {
    1: {
        "codigo": 1,
        "codigo_str": "01",
        "nombre": "Guatemala",
        "nombre_ascii": "GUATEMALA",
        "iso": "GT-GU",
        "region_id": 1,
        "region_nombre": "Metropolitana",
        "cabecera": "Guatemala",
    },
    2: {
        "codigo": 2,
        "codigo_str": "02",
        "nombre": "El Progreso",
        "nombre_ascii": "EL PROGRESO",
        "iso": "GT-PR",
        "region_id": 3,
        "region_nombre": "Nororiente",
        "cabecera": "Guastatoya",
    },
    3: {
        "codigo": 3,
        "codigo_str": "03",
        "nombre": "Sacatepéquez",
        "nombre_ascii": "SACATEPEQUEZ",
        "iso": "GT-SA",
        "region_id": 5,
        "region_nombre": "Central",
        "cabecera": "Antigua Guatemala",
    },
    4: {
        "codigo": 4,
        "codigo_str": "04",
        "nombre": "Chimaltenango",
        "nombre_ascii": "CHIMALTENANGO",
        "iso": "GT-CM",
        "region_id": 5,
        "region_nombre": "Central",
        "cabecera": "Chimaltenango",
    },
    5: {
        "codigo": 5,
        "codigo_str": "05",
        "nombre": "Escuintla",
        "nombre_ascii": "ESCUINTLA",
        "iso": "GT-ES",
        "region_id": 5,
        "region_nombre": "Central",
        "cabecera": "Escuintla",
    },
    6: {
        "codigo": 6,
        "codigo_str": "06",
        "nombre": "Santa Rosa",
        "nombre_ascii": "SANTA ROSA",
        "iso": "GT-SR",
        "region_id": 4,
        "region_nombre": "Suroriente",
        "cabecera": "Cuilapa",
    },
    7: {
        "codigo": 7,
        "codigo_str": "07",
        "nombre": "Sololá",
        "nombre_ascii": "SOLOLA",
        "iso": "GT-SO",
        "region_id": 6,
        "region_nombre": "Suroccidente",
        "cabecera": "Sololá",
    },
    8: {
        "codigo": 8,
        "codigo_str": "08",
        "nombre": "Totonicapán",
        "nombre_ascii": "TOTONICAPAN",
        "iso": "GT-TO",
        "region_id": 6,
        "region_nombre": "Suroccidente",
        "cabecera": "Totonicapán",
    },
    9: {
        "codigo": 9,
        "codigo_str": "09",
        "nombre": "Quetzaltenango",
        "nombre_ascii": "QUETZALTENANGO",
        "iso": "GT-QZ",
        "region_id": 6,
        "region_nombre": "Suroccidente",
        "cabecera": "Quetzaltenango",
    },
    10: {
        "codigo": 10,
        "codigo_str": "10",
        "nombre": "Suchitepéquez",
        "nombre_ascii": "SUCHITEPEQUEZ",
        "iso": "GT-SU",
        "region_id": 6,
        "region_nombre": "Suroccidente",
        "cabecera": "Mazatenango",
    },
    11: {
        "codigo": 11,
        "codigo_str": "11",
        "nombre": "Retalhuleu",
        "nombre_ascii": "RETALHULEU",
        "iso": "GT-RE",
        "region_id": 6,
        "region_nombre": "Suroccidente",
        "cabecera": "Retalhuleu",
    },
    12: {
        "codigo": 12,
        "codigo_str": "12",
        "nombre": "San Marcos",
        "nombre_ascii": "SAN MARCOS",
        "iso": "GT-SM",
        "region_id": 6,
        "region_nombre": "Suroccidente",
        "cabecera": "San Marcos",
    },
    13: {
        "codigo": 13,
        "codigo_str": "13",
        "nombre": "Huehuetenango",
        "nombre_ascii": "HUEHUETENANGO",
        "iso": "GT-HU",
        "region_id": 7,
        "region_nombre": "Noroccidente",
        "cabecera": "Huehuetenango",
    },
    14: {
        "codigo": 14,
        "codigo_str": "14",
        "nombre": "Quiché",
        "nombre_ascii": "QUICHE",
        "iso": "GT-QC",
        "region_id": 7,
        "region_nombre": "Noroccidente",
        "cabecera": "Santa Cruz del Quiché",
    },
    15: {
        "codigo": 15,
        "codigo_str": "15",
        "nombre": "Baja Verapaz",
        "nombre_ascii": "BAJA VERAPAZ",
        "iso": "GT-BV",
        "region_id": 2,
        "region_nombre": "Norte",
        "cabecera": "Salamá",
    },
    16: {
        "codigo": 16,
        "codigo_str": "16",
        "nombre": "Alta Verapaz",
        "nombre_ascii": "ALTA VERAPAZ",
        "iso": "GT-AV",
        "region_id": 2,
        "region_nombre": "Norte",
        "cabecera": "Cobán",
    },
    17: {
        "codigo": 17,
        "codigo_str": "17",
        "nombre": "Petén",
        "nombre_ascii": "PETEN",
        "iso": "GT-PE",
        "region_id": 8,
        "region_nombre": "Petén",
        "cabecera": "Flores",
    },
    18: {
        "codigo": 18,
        "codigo_str": "18",
        "nombre": "Izabal",
        "nombre_ascii": "IZABAL",
        "iso": "GT-IZ",
        "region_id": 3,
        "region_nombre": "Nororiente",
        "cabecera": "Puerto Barrios",
    },
    19: {
        "codigo": 19,
        "codigo_str": "19",
        "nombre": "Zacapa",
        "nombre_ascii": "ZACAPA",
        "iso": "GT-ZA",
        "region_id": 3,
        "region_nombre": "Nororiente",
        "cabecera": "Zacapa",
    },
    20: {
        "codigo": 20,
        "codigo_str": "20",
        "nombre": "Chiquimula",
        "nombre_ascii": "CHIQUIMULA",
        "iso": "GT-CQ",
        "region_id": 3,
        "region_nombre": "Nororiente",
        "cabecera": "Chiquimula",
    },
    21: {
        "codigo": 21,
        "codigo_str": "21",
        "nombre": "Jalapa",
        "nombre_ascii": "JALAPA",
        "iso": "GT-JA",
        "region_id": 4,
        "region_nombre": "Suroriente",
        "cabecera": "Jalapa",
    },
    22: {
        "codigo": 22,
        "codigo_str": "22",
        "nombre": "Jutiapa",
        "nombre_ascii": "JUTIAPA",
        "iso": "GT-JU",
        "region_id": 4,
        "region_nombre": "Suroriente",
        "cabecera": "Jutiapa",
    },
}

# 8 regiones socioeconomicas oficiales
REGIONES_SOCIOECONOMICAS: Dict[int, Dict[str, Any]] = {
    1: {"id": 1, "nombre": "Metropolitana", "deptos": [1]},
    2: {"id": 2, "nombre": "Norte", "deptos": [15, 16]},
    3: {"id": 3, "nombre": "Nororiente", "deptos": [2, 18, 19, 20]},
    4: {"id": 4, "nombre": "Suroriente", "deptos": [6, 21, 22]},
    5: {"id": 5, "nombre": "Central", "deptos": [3, 4, 5]},
    6: {"id": 6, "nombre": "Suroccidente", "deptos": [7, 8, 9, 10, 11, 12]},
    7: {"id": 7, "nombre": "Noroccidente", "deptos": [13, 14]},
    8: {"id": 8, "nombre": "Petén", "deptos": [17]},
}

# indice rapido de busqueda por nombre normalizado
_NAME_LOOKUP: Dict[str, Dict[str, Any]] = {}
for code, data in DEPARTAMENTOS_INE.items():
    _NAME_LOOKUP[strip_accents(data["nombre"])] = data
    _NAME_LOOKUP[str(code)] = data
    _NAME_LOOKUP[data["codigo_str"]] = data
    _NAME_LOOKUP[data["iso"]] = data


def normalize_department(value: Union[str, int, float]) -> Optional[Dict[str, Any]]:
    """buscar y devolver registro normalizado de un departamento por codigo, nombre o iso."""
    if value is None:
        return None
        
    if isinstance(value, (int, float)):
        try:
            return DEPARTAMENTOS_INE.get(int(value))
        except (ValueError, OverflowError):
            pass
            
    val_str = str(value).strip()
    if not val_str:
        return None
        
    # intento directo por entero o decimal
    try:
        val_int = int(float(val_str))
        if val_int in DEPARTAMENTOS_INE:
            return DEPARTAMENTOS_INE[val_int]
    except (ValueError, OverflowError):
        pass
        
    # busqueda por nombre limpio
    norm_key = strip_accents(val_str)
    return _NAME_LOOKUP.get(norm_key)


def get_department_code(value: Union[str, int]) -> Optional[int]:
    """obtener el codigo numerico oficial (1 a 22) de un departamento."""
    rec = normalize_department(value)
    return rec["codigo"] if rec else None


def get_department_region(value: Union[str, int]) -> Optional[int]:
    """obtener el id de la region socioeconomica (1 a 8) de un departamento."""
    rec = normalize_department(value)
    return rec["region_id"] if rec else None


def get_all_departments() -> List[Dict[str, Any]]:
    """devolver lista completa ordenada de los 22 departamentos."""
    return [DEPARTAMENTOS_INE[k] for k in sorted(DEPARTAMENTOS_INE.keys())]


# alias compatibles
normalize_depto = normalize_department
get_depto_code = get_department_code
get_depto_region = get_department_region
get_all_departamentos = get_all_departments
