"""Limpieza, normalización y validación de inscripciones."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from src.matcher import find_column, normalize_key
from src.models import DetectedColumns


ALIASES = {
    "identification": [
        "Numero identificacion",
        "Número de identificación",
        "Numero de identificacion",
        "Identificacion",
        "Identificación",
        "Documento",
        "Número de ID",
        "Numero de ID",
        "Cedula",
        "Cédula",
        "DNI",
        "ID",
    ],
    "names": ["Nombres", "Nombre", "Nombres completos", "Nombre estudiante"],
    "surnames": ["Apellidos", "Apellido", "Apellido(s)", "Apellidos estudiante"],
    "school": [
        "Nombre del colegio o institución educativa",
        "Nombre del colegio o institucion educativa",
        "Nombre del colegio",
        "Colegio",
        "Institución educativa",
        "Institucion educativa",
    ],
    "department": ["Departamento", "Departamento residencia"],
    "municipality": ["Municipio", "Municipio residencia", "Ciudad"],
    "level": [
        "Nivel",
        "Nivel (junio,basico, medio o avanzado)",
        "Nivel (junior, basico, medio o avanzado)",
        "Level",
    ],
    "grade": ["Grado", "Curso", "Grade"],
    "sector": [
        "Sector",
        "Tipo de colegio",
        "Tipo colegio",
        "Publico privado",
        "Público privado",
        "Caracter",
        "Carácter",
    ],
    "gender": ["Genero", "Género", "Sexo", "Gender"],
}

CANONICAL_ID = "Numero identificacion"
CANONICAL_NAMES = "Nombres"
CANONICAL_SURNAMES = "Apellidos"
CANONICAL_SCHOOL = "Nombre del colegio o institución educativa"
CANONICAL_DEPARTMENT = "Departamento"
CANONICAL_MUNICIPALITY = "Municipio"


def _text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).strip().split())


def normalize_identification(value: object) -> str:
    """Quita separadores comunes únicamente cuando el resultado sigue siendo numérico."""
    clean = _text(value)
    if re.fullmatch(r"-\d+", clean):
        return clean
    compact = re.sub(r"[\s.\-]", "", clean)
    return compact if compact.isdigit() else clean


def _series(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None:
        return pd.Series("", index=frame.index, dtype="object")
    return frame[column].fillna("").astype(str)


def _load_normalization_maps() -> dict[str, dict[str, str]]:
    path = Path(__file__).resolve().parents[1] / "config" / "normalization.json"
    if not path.exists():
        return {}
    try:
        raw_maps = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        category: {normalize_key(key): str(value).strip() for key, value in values.items()}
        for category, values in raw_maps.items()
        if isinstance(values, dict)
    }


def detect_columns(frame: pd.DataFrame) -> DetectedColumns:
    columns = frame.columns
    return DetectedColumns(
        identification=find_column(columns, ALIASES["identification"]),
        names=find_column(columns, ALIASES["names"]),
        surnames=find_column(columns, ALIASES["surnames"]),
        school=find_column(columns, ALIASES["school"], allow_partial=True),
        department=find_column(columns, ALIASES["department"], allow_partial=True),
        municipality=find_column(columns, ALIASES["municipality"], allow_partial=True),
        level=find_column(columns, ALIASES["level"], allow_partial=True),
        grade=find_column(columns, ALIASES["grade"]),
        sector=find_column(columns, ALIASES["sector"]),
        gender=find_column(columns, ALIASES["gender"]),
    )


def _canonical_value(value: object, mapping: dict[str, str], *, title: bool = False) -> str:
    clean = _text(value)
    if not clean:
        return ""
    mapped = mapping.get(normalize_key(clean))
    if mapped:
        return mapped
    return clean.title() if title else clean


def _grade_number(value: object) -> str:
    clean = normalize_key(value)
    word_grades = {
        "cuarto": "4",
        "quinto": "5",
        "sexto": "6",
        "septimo": "7",
        "octavo": "8",
        "noveno": "9",
        "decimo": "10",
        "once": "11",
    }
    for token, number in word_grades.items():
        if re.search(rf"\b{token}\b", clean):
            return number
    match = re.search(r"(?<!\d)(1[01]|[4-9])(?!\d)", clean)
    return match.group(1) if match else ""


def _normalized_level(value: object, grade: object) -> str:
    clean = normalize_key(value)
    word_levels = {
        "junio": "Junior",
        "junior": "Junior",
        "juniors": "Junior",
        "basico": "Básico",
        "medio": "Medio",
        "avanzado": "Avanzado",
    }
    for token, canonical in word_levels.items():
        if re.search(rf"\b{re.escape(token)}\b", clean):
            return canonical

    number = _grade_number(value) or _grade_number(grade)
    if number in {"4", "5"}:
        return "Junior"
    if number in {"6", "7"}:
        return "Básico"
    if number in {"8", "9"}:
        return "Medio"
    if number in {"10", "11"}:
        return "Avanzado"
    return "No definido"


def _school_type(value: object) -> str:
    clean = normalize_key(value)
    if not clean or clean == "individual":
        return "No definido"
    if clean in {"oficial", "publico", "publica"} or "publico" in clean:
        return "Público"
    private_terms = {"privado", "privada", "particular", "no oficial"}
    if any(term in clean for term in private_terms):
        return "Privado"
    return "No definido"


def _gender(value: object) -> str:
    clean = normalize_key(value)
    if clean in {"m", "masculino", "male", "hombre"}:
        return "Hombre"
    if clean in {"f", "femenino", "female", "mujer"}:
        return "Mujer"
    return "Otro / No definido"


class Cleaner:
    """Transforma archivos heterogéneos a columnas canónicas sin perder el original."""

    @classmethod
    def prepare(cls, frame: pd.DataFrame) -> tuple[pd.DataFrame, DetectedColumns]:
        columns = detect_columns(frame)
        maps = _load_normalization_maps()
        cleaned = frame.copy().fillna("")
        cleaned["_fila_origen"] = [index + 2 for index in range(len(cleaned))]
        cleaned = cleaned[["_fila_origen", *[c for c in cleaned.columns if c != "_fila_origen"]]]

        ids = _series(cleaned, columns.identification).map(normalize_identification)
        names = _series(cleaned, columns.names).map(lambda value: _text(value).upper())
        surnames = _series(cleaned, columns.surnames).map(lambda value: _text(value).upper())
        schools = _series(cleaned, columns.school).map(
            lambda value: _canonical_value(value, maps.get("schools", {}))
        )
        departments = _series(cleaned, columns.department).map(
            lambda value: _canonical_value(value, maps.get("departments", {}), title=True)
        )
        municipalities = _series(cleaned, columns.municipality).map(
            lambda value: _canonical_value(value, maps.get("municipalities", {}), title=True)
        )
        original_grades = _series(cleaned, columns.grade)
        original_levels = _series(cleaned, columns.level)
        grades = original_grades.map(lambda value: _grade_number(value) or _text(value))
        levels = pd.Series(
            [
                _normalized_level(level, grade)
                for level, grade in zip(original_levels, original_grades)
            ],
            index=cleaned.index,
            dtype="object",
        )

        cleaned[CANONICAL_ID] = ids
        cleaned[CANONICAL_NAMES] = names
        cleaned[CANONICAL_SURNAMES] = surnames
        cleaned[CANONICAL_SCHOOL] = schools
        cleaned[CANONICAL_DEPARTMENT] = departments
        cleaned[CANONICAL_MUNICIPALITY] = municipalities
        cleaned["Grado"] = grades
        cleaned["Nivel"] = levels
        cleaned["tipo_colegio"] = _series(cleaned, columns.sector).map(_school_type)
        cleaned["genero_normalizado"] = _series(cleaned, columns.gender).map(_gender)
        return cleaned, columns


def detect_problems(frame: pd.DataFrame) -> pd.DataFrame:
    """Devuelve las filas problemáticas con todas sus razones, incluidos duplicados."""
    if frame.empty:
        return pd.DataFrame(columns=[*frame.columns, "columnas_con_error", "errores"])

    ids = frame[CANONICAL_ID].map(_text)
    valid_ids = ids.where(ids.str.fullmatch(r"\d+", na=False), "")
    duplicated = valid_ids.ne("") & valid_ids.duplicated(keep=False)
    rows: list[dict[str, object]] = []

    for position, (_, row) in enumerate(frame.iterrows()):
        reasons: list[str] = []
        error_columns: list[str] = []

        def add_error(column: str, reason: str) -> None:
            reasons.append(reason)
            if column not in error_columns:
                error_columns.append(column)

        identification = ids.iloc[position]
        if not _text(row.get(CANONICAL_NAMES, "")):
            add_error(CANONICAL_NAMES, "Nombre faltante")
        if not _text(row.get(CANONICAL_SURNAMES, "")):
            add_error(CANONICAL_SURNAMES, "Apellido faltante")
        if not identification:
            add_error(CANONICAL_ID, "Identificación faltante")
        elif not identification.isdigit():
            add_error(CANONICAL_ID, "Identificación no numérica")
        elif not 6 <= len(identification) <= 12:
            add_error(CANONICAL_ID, "Longitud de identificación inusual")
        if duplicated.iloc[position]:
            add_error(CANONICAL_ID, "Identificación duplicada")
        if not _text(row.get(CANONICAL_SCHOOL, "")):
            add_error(CANONICAL_SCHOOL, "Colegio faltante")
        if not _text(row.get(CANONICAL_DEPARTMENT, "")):
            add_error(CANONICAL_DEPARTMENT, "Departamento faltante")
        if not _text(row.get(CANONICAL_MUNICIPALITY, "")):
            add_error(CANONICAL_MUNICIPALITY, "Municipio faltante")
        if row.get("Nivel") == "No definido":
            add_error("Nivel", "Nivel no reconocido")

        if reasons:
            result = row.to_dict()
            result["columnas_con_error"] = "; ".join(error_columns)
            result["errores"] = "; ".join(reasons)
            rows.append(result)

    return pd.DataFrame(
        rows,
        columns=[*frame.columns, "columnas_con_error", "errores"],
    )
