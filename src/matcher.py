"""Utilidades seguras para reconocer encabezados de archivos externos."""

import re
import unicodedata
from collections.abc import Iterable


def normalize_key(value: object) -> str:
    """Convierte texto a una clave comparable sin acentos ni puntuación."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value).strip())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return " ".join(text.split())


def find_column(
    columns: Iterable[object],
    aliases: Iterable[str],
    *,
    allow_partial: bool = False,
) -> str | None:
    """Busca primero coincidencias exactas y, opcionalmente, parciales.

    Los alias cortos no se comparan parcialmente, para impedir que ``id``
    termine coincidiendo con ``Apellidos`` u otro encabezado inesperado.
    """
    normalized_columns = [(str(column), normalize_key(column)) for column in columns]
    normalized_aliases = [normalize_key(alias) for alias in aliases]
    lookup = {normalized: original for original, normalized in normalized_columns}

    for alias in normalized_aliases:
        if alias in lookup:
            return lookup[alias]

    if not allow_partial:
        return None

    candidates: list[tuple[int, str]] = []
    for original, column_key in normalized_columns:
        for alias in normalized_aliases:
            if len(alias) >= 4 and alias in column_key:
                candidates.append((len(alias), original))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]
