"""Modelos compartidos por el proceso de inscripciones."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DetectedColumns:
    """Columnas del archivo de origen reconocidas por la aplicación."""

    identification: Optional[str] = None
    names: Optional[str] = None
    surnames: Optional[str] = None
    school: Optional[str] = None
    department: Optional[str] = None
    municipality: Optional[str] = None
    level: Optional[str] = None
    grade: Optional[str] = None
    sector: Optional[str] = None
    gender: Optional[str] = None

    def required_missing(self) -> list[str]:
        required = {
            "identification": "Identificación",
            "names": "Nombres",
            "surnames": "Apellidos",
            "school": "Colegio o institución educativa",
            "department": "Departamento",
            "municipality": "Municipio",
        }
        return [label for field, label in required.items() if getattr(self, field) is None]
