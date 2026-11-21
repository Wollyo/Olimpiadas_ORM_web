"""Carga robusta de archivos tabulares de inscripciones."""

from io import BytesIO
from pathlib import Path

import pandas as pd

from src.utils import make_unique_column_names


class DataLoadError(ValueError):
    """Error legible al cargar un archivo de inscripciones."""


class DataLoader:
    """Carga CSV y XLSX conservando identificadores como texto."""

    SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}

    @classmethod
    def from_path(cls, path: str | Path) -> pd.DataFrame:
        source = Path(path)
        return cls.from_bytes(source.name, source.read_bytes())

    @classmethod
    def from_bytes(cls, file_name: str, content: bytes) -> pd.DataFrame:
        extension = Path(file_name).suffix.lower()
        if extension not in cls.SUPPORTED_EXTENSIONS:
            raise DataLoadError("Formato no soportado. Usa CSV o XLSX.")
        if not content:
            raise DataLoadError("El archivo está vacío.")

        try:
            if extension == ".csv":
                frame = cls._read_csv(content)
            else:
                frame = pd.read_excel(
                    BytesIO(content),
                    dtype=str,
                    keep_default_na=False,
                )
        except ImportError as exc:
            raise DataLoadError(
                f"Falta la dependencia openpyxl para leer archivos {extension}."
            ) from exc
        except Exception as exc:
            raise DataLoadError(f"No se pudo leer el archivo: {exc}") from exc

        # Dos encabezados pueden quedar iguales al retirar espacios. PyArrow no
        # admite nombres duplicados al mostrar el DataFrame en Streamlit.
        frame.columns = make_unique_column_names(frame.columns)
        populated_rows = frame.fillna("").astype(str).apply(
            lambda column: column.str.strip()
        ).ne("").any(axis=1)
        frame = frame.loc[populated_rows].reset_index(drop=True)
        empty_unnamed = [
            column
            for column in frame.columns
            if column.lower().startswith("unnamed:")
            and frame[column].fillna("").astype(str).str.strip().eq("").all()
        ]
        if empty_unnamed:
            frame = frame.drop(columns=empty_unnamed)
        return frame.fillna("")

    @staticmethod
    def _read_csv(content: bytes) -> pd.DataFrame:
        errors: list[Exception] = []
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return pd.read_csv(
                    BytesIO(content),
                    dtype=str,
                    keep_default_na=False,
                    sep=None,
                    engine="python",
                    encoding=encoding,
                )
            except UnicodeDecodeError as exc:
                errors.append(exc)
        raise DataLoadError(f"No se reconoció la codificación del CSV: {errors[-1]}")
