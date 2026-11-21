"""Utilidades compartidas para el tratamiento seguro de datos tabulares."""

from collections.abc import Iterable


def make_unique_column_names(columns: Iterable[object]) -> list[str]:
    """Devuelve encabezados limpios y únicos sin descartar ninguna columna."""
    unique: list[str] = []
    used: set[str] = set()

    for column in columns:
        base = str(column).strip() or "Columna sin nombre"
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base} ({suffix})"
            suffix += 1
        used.add(candidate)
        unique.append(candidate)

    return unique
