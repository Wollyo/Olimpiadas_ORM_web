"""Preparación y cruce de calificaciones con el consolidado de inscritos."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.cleaner import (
    CANONICAL_DEPARTMENT,
    CANONICAL_ID,
    CANONICAL_MUNICIPALITY,
    CANONICAL_NAMES,
    CANONICAL_SCHOOL,
    CANONICAL_SURNAMES,
    normalize_identification,
)
from src.matcher import find_column, normalize_key


class GradeFileError(ValueError):
    """Indica que un archivo de calificaciones no es seguro para cruzar."""


@dataclass(frozen=True)
class PreparedGradeFile:
    frame: pd.DataFrame
    excluded_rows: pd.DataFrame
    level: str
    test_name: str
    maximum_score: float | None
    source_name: str
    administrative_rows: int = 0


ID_ALIASES = [
    "Número de ID",
    "Numero de ID",
    "Numero identificacion",
    "Número de identificación",
    "Identificación",
    "Documento",
    "ID",
]
GRADE_ALIASES = ["Calificación", "Calificacion", "Nota", "Puntaje", "Score"]


def _text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).strip().split())


def _parse_decimal(value: object) -> float | None:
    text = _text(value)
    if text in {"-", "--"}:
        return 0.0
    if not text:
        return None
    text = text.replace("%", "").replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _maximum_from_header(header: str) -> float | None:
    match = re.search(r"/\s*(\d+(?:[.,]\d+)?)", header)
    return _parse_decimal(match.group(1)) if match else None


def _test_name(file_name: str) -> str:
    stem = Path(file_name).stem
    match = re.search(r"prueba\s*#?\s*(\d+)", stem, flags=re.IGNORECASE)
    return f"Prueba {match.group(1)}" if match else "Prueba"


def _optional_column(frame: pd.DataFrame, aliases: list[str]) -> str | None:
    return find_column(frame.columns, aliases, allow_partial=True)


def prepare_grade_file(
    frame: pd.DataFrame,
    *,
    level: str,
    file_name: str,
) -> PreparedGradeFile:
    """Valida un reporte de notas y devuelve solamente campos útiles para el cruce."""
    if frame.empty:
        raise GradeFileError(f"El archivo de {level} no contiene registros.")

    id_column = find_column(frame.columns, ID_ALIASES)
    grade_column = find_column(frame.columns, GRADE_ALIASES, allow_partial=True)
    if id_column is None:
        raise GradeFileError(f"En {level} no se encontró la columna de identificación.")
    if grade_column is None:
        raise GradeFileError(f"En {level} no se encontró una columna de calificación o nota.")

    working = frame.copy()
    working["_fila_reporte"] = range(2, len(working) + 2)
    surname_column = _optional_column(working, ["Apellido(s)", "Apellidos", "Apellido"])
    name_column = _optional_column(working, ["Nombre", "Nombres"])
    ids = working[id_column].map(normalize_identification)
    summary_text = pd.Series("", index=working.index, dtype="object")
    if surname_column is not None:
        summary_text = summary_text + " " + working[surname_column].map(_text)
    if name_column is not None:
        summary_text = summary_text + " " + working[name_column].map(_text)
    administrative_row = ids.eq("") & summary_text.map(normalize_key).str.contains(
        r"\b(?:promedio|media|total|resumen)\b",
        regex=True,
    )
    administrative_count = int(administrative_row.sum())
    working = working.loc[~administrative_row].copy()
    ids = working[id_column].map(normalize_identification)
    raw_grades = working[grade_column].map(_text)
    dash_grades = raw_grades.isin({"-", "--"})
    grades = raw_grades.map(_parse_decimal)

    maximum = _maximum_from_header(grade_column)
    reasons = pd.Series("", index=working.index, dtype="object")
    reasons.loc[ids.eq("")] = "Identificación vacía"
    reasons.loc[ids.ne("") & ~ids.str.fullmatch(r"\d+", na=False)] = (
        "Identificación no estudiantil (posible monitor o profesor)"
    )
    reasons.loc[reasons.eq("") & grades.isna()] = "Calificación vacía o inválida"
    if maximum is not None:
        out_of_range = grades.lt(0) | grades.gt(maximum)
        reasons.loc[reasons.eq("") & out_of_range] = (
            f"Calificación fuera del rango 0–{maximum:g}"
        )

    initially_valid = reasons.eq("")
    duplicated = initially_valid & ids.duplicated(keep=False)
    if duplicated.any():
        duplicate_candidates = pd.DataFrame(
            {
                "id": ids.loc[duplicated],
                "grade": grades.loc[duplicated],
                "row": working.loc[duplicated, "_fila_reporte"],
            }
        ).sort_values(["id", "grade", "row"], ascending=[True, False, True])
        keep_indices = set(duplicate_candidates.groupby("id", sort=False).head(1).index)
        discarded_duplicates = duplicated & ~working.index.isin(keep_indices)
        reasons.loc[discarded_duplicates] = (
            "Intento duplicado; se conservó la calificación más alta"
        )

    valid = reasons.eq("")
    if not valid.any():
        raise GradeFileError(
            f"El archivo de {level} no contiene calificaciones estudiantiles válidas."
        )

    valid_frame = working.loc[valid]
    valid_ids = ids.loc[valid]
    valid_grades = grades.loc[valid]

    excluded_frame = working.loc[~valid]
    excluded = pd.DataFrame(
        {
            "Fila del archivo": excluded_frame["_fila_reporte"],
            "Nivel del archivo": level,
            "Número de ID": excluded_frame[id_column].map(_text),
            "Nombre": (
                excluded_frame[name_column].map(_text)
                if name_column is not None
                else ""
            ),
            "Apellido(s)": (
                excluded_frame[surname_column].map(_text)
                if surname_column is not None
                else ""
            ),
            "Motivo de exclusión": reasons.loc[~valid],
        }
    ).reset_index(drop=True)

    result = pd.DataFrame(
        {
            CANONICAL_ID: valid_ids,
            "Nota de la prueba": valid_grades,
            "Nota máxima": maximum if maximum is not None else pd.NA,
            "Porcentaje de la prueba": (
                valid_grades.div(maximum).mul(100).round(2) if maximum else pd.NA
            ),
            "Nivel del archivo de notas": level,
            "Calificación originalmente en guion": dash_grades.loc[valid],
        }
    )

    optional_fields = {
        "Estado de la prueba": ["Estado", "Status"],
        "Inicio de la prueba": ["Comenzado", "Iniciado", "Started"],
        "Finalización de la prueba": ["Finalizado", "Terminado", "Finished"],
        "Duración de la prueba": ["Duración", "Duracion", "Tiempo", "Duration"],
    }
    for output_name, aliases in optional_fields.items():
        source = _optional_column(valid_frame, aliases)
        if source is not None:
            result[output_name] = valid_frame[source].map(_text)

    return PreparedGradeFile(
        frame=result.reset_index(drop=True),
        excluded_rows=excluded,
        level=level,
        test_name=_test_name(file_name),
        maximum_score=maximum,
        source_name=file_name,
        administrative_rows=administrative_count,
    )


def combine_grade_files(files: list[PreparedGradeFile]) -> tuple[pd.DataFrame, str]:
    if not files:
        raise GradeFileError("No se cargaron archivos de calificaciones.")
    test_names = {file.test_name for file in files}
    if len(test_names) != 1:
        names = ", ".join(sorted(test_names))
        raise GradeFileError(f"Los archivos parecen pertenecer a pruebas diferentes: {names}.")

    combined = pd.concat([file.frame for file in files], ignore_index=True)
    repeated = combined[CANONICAL_ID].duplicated(keep=False)
    if repeated.any():
        raise GradeFileError(
            f"Hay {int(repeated.sum())} filas cuyos ID aparecen en más de un archivo de nivel."
        )
    return combined, next(iter(test_names))


def merge_with_registrations(
    registrations: pd.DataFrame,
    grades: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Cruza por ID y devuelve consolidado, notas sin inscripción y niveles incorrectos."""
    registration_ids = set(registrations[CANONICAL_ID].astype(str))
    unmatched = grades[~grades[CANONICAL_ID].isin(registration_ids)].copy()
    matched_grades = grades[grades[CANONICAL_ID].isin(registration_ids)].copy()
    merged = registrations.merge(
        matched_grades,
        on=CANONICAL_ID,
        how="left",
        validate="one_to_one",
    )

    has_grade_row = merged["Nivel del archivo de notas"].notna()
    level_mismatch = has_grade_row & (
        merged["Nivel"].map(normalize_key)
        != merged["Nivel del archivo de notas"].map(normalize_key)
    )
    mismatches = merged[level_mismatch].copy()

    maximum_by_level = (
        grades.dropna(subset=["Nota máxima"])
        .groupby("Nivel del archivo de notas")["Nota máxima"]
        .first()
        .to_dict()
    )
    dash_grade = merged["Calificación originalmente en guion"].fillna(False).astype(bool)
    presented = has_grade_row & ~dash_grade
    merged["Presentó la prueba"] = presented
    merged["Nota máxima"] = merged["Nota máxima"].fillna(
        merged["Nivel"].map(maximum_by_level)
    )
    merged["Nota de la prueba"] = merged["Nota de la prueba"].fillna(0.0)
    merged["Porcentaje de la prueba"] = merged["Porcentaje de la prueba"].fillna(0.0)
    merged["Estado de presentación"] = presented.map(
        {True: "Presentó", False: "Sin calificación / no presentó"}
    )
    if "Estado de la prueba" in merged.columns:
        merged["Estado de la prueba"] = merged["Estado de la prueba"].fillna(
            "Sin calificación / no presentó"
        )
    return merged, unmatched, mismatches


def _export_series(frame: pd.DataFrame, aliases: list[str]) -> pd.Series:
    column = find_column(frame.columns, aliases)
    if column is None:
        return pd.Series("", index=frame.index, dtype="object")
    return frame[column].fillna("").map(_text)


def _test_number(column: str) -> int:
    match = re.fullmatch(r"Prueba\s+(\d+)", str(column), flags=re.IGNORECASE)
    return int(match.group(1)) if match else 10**9


def build_results_export(merged: pd.DataFrame, test_name: str) -> pd.DataFrame:
    """Crea el resultado compacto, conserva pruebas anteriores y recalcula el total."""
    if not re.fullmatch(r"Prueba\s+\d+", test_name, flags=re.IGNORECASE):
        raise GradeFileError(
            "No se pudo identificar el número de prueba en los nombres de archivo. "
            "Incluye textos como 'Prueba #1' o 'Prueba 2'."
        )

    existing_tests = sorted(
        [
            str(column)
            for column in merged.columns
            if re.fullmatch(r"Prueba\s+\d+", str(column), flags=re.IGNORECASE)
        ],
        key=_test_number,
    )
    if any(column.casefold() == test_name.casefold() for column in existing_tests):
        raise GradeFileError(
            f"El consolidado ya contiene {test_name}. No se sobrescribió ninguna nota."
        )

    result = pd.DataFrame(index=merged.index)
    result["Número de ID"] = _export_series(merged, [CANONICAL_ID])
    result["Nombre"] = _export_series(merged, [CANONICAL_NAMES, "Nombre"])
    result["Apellido(s)"] = _export_series(merged, [CANONICAL_SURNAMES, "Apellido(s)"])
    result["Correo electrónico"] = _export_series(
        merged,
        [
            "Email de contacto",
            "Correo electrónico",
            "Dirección de correo electrónico",
            "Email",
        ],
    )
    result["Nivel"] = _export_series(merged, ["Nivel"])
    result["Grado"] = _export_series(merged, ["Grado"])
    result["Codigo ORM"] = _export_series(merged, ["Codigo ORM", "Código ORM"])
    result["Colegio"] = _export_series(merged, [CANONICAL_SCHOOL, "Colegio"])
    result["Departamento"] = _export_series(merged, [CANONICAL_DEPARTMENT])
    result["Ciudad"] = _export_series(merged, [CANONICAL_MUNICIPALITY, "Ciudad"])

    for column in existing_tests:
        original = merged[column].fillna("").map(_text)
        parsed = original.map(_parse_decimal)
        invalid = original.ne("") & parsed.isna()
        if invalid.any():
            raise GradeFileError(
                f"La columna {column} contiene {int(invalid.sum())} notas no numéricas."
            )
        result[f"Prueba {_test_number(column)}"] = parsed.fillna(0.0)

    result[test_name] = pd.to_numeric(
        merged["Nota de la prueba"], errors="coerce"
    ).fillna(0.0)
    test_columns = sorted(
        [column for column in result.columns if re.fullmatch(r"Prueba\s+\d+", column)],
        key=_test_number,
    )
    result["Nota_Total"] = result[test_columns].sum(axis=1).round(2)
    return result.reset_index(drop=True)
