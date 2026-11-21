"""Genera datos sintéticos para probar el cruce completo de calificaciones."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "examples" / "merge_test"


def registrations() -> pd.DataFrame:
    levels = [
        ("Junior", ["4", "5", "4"]),
        ("Básico", ["6", "7", "6"]),
        ("Medio", ["8", "9", "8"]),
        ("Avanzado", ["10", "11", "10"]),
    ]
    places = [
        ("Valle del Cauca", "Cali", "Colegio Ejemplo Cali"),
        ("Valle del Cauca", "Palmira", "Institución Educativa Prueba"),
        ("Cauca", "Popayán", "Colegio Demostración Popayán"),
    ]
    rows = []
    counter = 1
    for level_index, (level, grades) in enumerate(levels, start=1):
        for position, grade in enumerate(grades):
            department, municipality, school = places[position]
            rows.append(
                {
                    "Numero identificacion": str(8000000 + counter),
                    "Nombres": f"ESTUDIANTE {counter:02d}",
                    "Apellidos": "DATOS DE PRUEBA",
                    "Email de contacto": f"estudiante{counter:02d}@example.test",
                    "Codigo ORM": f"ORM-{level_index:02d}-{counter:03d}",
                    "Genero": "F" if counter % 2 == 0 else "M",
                    "Nivel": level,
                    "Grado": grade,
                    "Nombre del colegio o institución educativa": school,
                    "Sector": "Oficial" if position != 1 else "Privado",
                    "Departamento": department,
                    "Municipio": municipality,
                }
            )
            counter += 1
    return pd.DataFrame(rows)


def moodle_grades(
    general: pd.DataFrame,
    level: str,
    *,
    test_number: int = 1,
    add_unmatched: bool = False,
) -> pd.DataFrame:
    level_students = general[general["Nivel"] == level]
    rows = []
    for position, (_, student) in enumerate(level_students.iterrows(), start=1):
        numeric_score = 48 + position * 12 + (test_number - 1) * 2
        score = "-" if position == 3 else numeric_score
        status = "-" if score == "-" else "Finalizado"
        detail_score = "-" if score == "-" else max(numeric_score - 50, 0)
        rows.append(
            {
                "Apellido(s)": student["Apellidos"],
                "Nombre": student["Nombres"],
                "Número de ID": student["Numero identificacion"],
                "Correo electrónico": student["Email de contacto"],
                "Estado": status,
                "Comenzado": "-" if score == "-" else "20/11/2026 08:00",
                "Finalizado": "-" if score == "-" else "20/11/2026 09:00",
                "Duración": "-" if score == "-" else "1 hora",
                "Calificación/80": score,
                "P. 1 /0": "-" if score == "-" else 0,
                "P. 2 /10": "-" if score == "-" else 10,
                "P. 3 /10": "-" if score == "-" else 10,
                "P. 4 /10": "-" if score == "-" else 10,
                "P. 5 /10": "-" if score == "-" else 10,
                "P. 6 /10": "-" if score == "-" else 10,
                "P. 7 /10": detail_score,
                "P. 8 /10": "-" if score == "-" else 0,
                "P. 9 /10": "-" if score == "-" else 0,
            }
        )
    if add_unmatched:
        rows.append(
            {
                "Apellido(s)": "NO EXISTE EN CONSOLIDADO",
                "Nombre": "USUARIO DEMOSTRACIÓN",
                "Número de ID": "9999999",
                "Correo electrónico": "noinscrito@example.test",
                "Estado": "Finalizado",
                "Comenzado": "20/11/2026 08:00",
                "Finalizado": "20/11/2026 09:00",
                "Duración": "1 hora",
                "Calificación/80": 55,
                "P. 1 /0": 0,
                "P. 2 /10": 10,
                "P. 3 /10": 10,
                "P. 4 /10": 10,
                "P. 5 /10": 10,
                "P. 6 /10": 10,
                "P. 7 /10": 5,
                "P. 8 /10": 0,
                "P. 9 /10": 0,
            }
        )
        rows.append(
            {
                "Apellido(s)": "MONITOR DE PRUEBA",
                "Nombre": "CUENTA TÉCNICA",
                "Número de ID": "-31",
                "Correo electrónico": "monitor@example.test",
                "Estado": "Finalizado",
                "Comenzado": "20/11/2026 08:00",
                "Finalizado": "20/11/2026 08:10",
                "Duración": "10 minutos",
                "Calificación/80": 80,
                "P. 1 /0": 0,
                "P. 2 /10": 10,
                "P. 3 /10": 10,
                "P. 4 /10": 10,
                "P. 5 /10": 10,
                "P. 6 /10": 10,
                "P. 7 /10": 10,
                "P. 8 /10": 10,
                "P. 9 /10": 10,
            }
        )
    rows.append(
        {
            "Apellido(s)": "Promedio general",
            "Nombre": "",
            "Número de ID": "",
            "Correo electrónico": "",
            "Estado": "",
            "Comenzado": "",
            "Finalizado": "",
            "Duración": "",
            "Calificación/80": 64,
            "P. 1 /0": 0,
            "P. 2 /10": 10,
            "P. 3 /10": 10,
            "P. 4 /10": 10,
            "P. 5 /10": 10,
            "P. 6 /10": 10,
            "P. 7 /10": 4,
            "P. 8 /10": 0,
            "P. 9 /10": 0,
        }
    )
    return pd.DataFrame(rows)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    general = registrations()
    files: list[Path] = []

    general_path = OUTPUT / "01_consolidado_general_limpio.xlsx"
    general.to_excel(general_path, index=False, sheet_name="Inscripciones")
    files.append(general_path)

    level_frames: dict[str, pd.DataFrame] = {}
    for number, level in enumerate(["Junior", "Básico", "Medio", "Avanzado"], start=2):
        frame = moodle_grades(general, level, add_unmatched=level == "Junior")
        level_frames[level] = frame
        safe_level = level.lower().replace("á", "a")
        path = OUTPUT / f"{number:02d}_Prueba #1_{safe_level}_calificaciones.xlsx"
        frame.to_excel(path, index=False, sheet_name="Calificaciones")
        files.append(path)

    combined_path = OUTPUT / "00_paquete_prueba_cruce.xlsx"
    with pd.ExcelWriter(combined_path, engine="openpyxl") as writer:
        general.to_excel(writer, index=False, sheet_name="Consolidado")
        for level, frame in level_frames.items():
            frame.to_excel(writer, index=False, sheet_name=f"Notas {level}")

    instructions = OUTPUT / "LEEME.txt"
    instructions.write_text(
        """PRUEBA DEL CRUCE DE CALIFICACIONES

Sube 01_consolidado_general_limpio.xlsx como consolidado general.
Sube los archivos 02 a 05 en su nivel correspondiente.

Resultado esperado:
- 12 inscripciones posibles.
- 8 estudiantes presentaron la prueba.
- 4 estudiantes no presentaron y deben recibir nota 0.
- 1 calificación de Junior no existe en el consolidado y debe aparecer como advertencia.
- 1 intento con ID -31 representa un monitor y debe excluirse con advertencia.
- Las filas 'Promedio general' deben ignorarse automáticamente.

00_paquete_prueba_cruce.xlsx sirve para revisar todos los datos en un solo libro,
pero la aplicación recibe los cinco archivos separados incluidos en este paquete.
""",
        encoding="utf-8",
    )
    files.append(instructions)

    zip_path = OUTPUT / "ejemplo_cruce_prueba_1.zip"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)

    score_by_id: dict[str, float] = {}
    for frame in level_frames.values():
        valid = frame[frame["Número de ID"].astype(str).str.fullmatch(r"\d+")]
        numeric_scores = pd.to_numeric(
            valid["Calificación/80"].replace({"-": 0, "--": 0}),
            errors="coerce",
        ).fillna(0.0)
        score_by_id.update(dict(zip(valid["Número de ID"].astype(str), numeric_scores)))
    expected = pd.DataFrame(
        {
            "Número de ID": general["Numero identificacion"],
            "Nombre": general["Nombres"],
            "Apellido(s)": general["Apellidos"],
            "Correo electrónico": general["Email de contacto"],
            "Nivel": general["Nivel"],
            "Grado": general["Grado"],
            "Codigo ORM": general["Codigo ORM"],
            "Colegio": general["Nombre del colegio o institución educativa"],
            "Departamento": general["Departamento"],
            "Ciudad": general["Municipio"],
        }
    )
    expected["Prueba 1"] = expected["Número de ID"].map(score_by_id).fillna(0.0)
    expected["Nota_Total"] = expected["Prueba 1"]
    expected_path = OUTPUT / "06_resultado_prueba_1_para_cargar.xlsx"
    expected.to_excel(expected_path, index=False, sheet_name="Resultados")

    second_test_files = [expected_path]
    for number, level in enumerate(["Junior", "Básico", "Medio", "Avanzado"], start=7):
        frame = moodle_grades(general, level, test_number=2)
        safe_level = level.lower().replace("á", "a")
        path = OUTPUT / f"{number:02d}_Prueba #2_{safe_level}_calificaciones.xlsx"
        frame.to_excel(path, index=False, sheet_name="Calificaciones")
        second_test_files.append(path)

    second_instructions = OUTPUT / "LEEME_PRUEBA_2.txt"
    second_instructions.write_text(
        """PRUEBA DE ACUMULACIÓN SIN SOBRESCRIBIR

Sube 06_resultado_prueba_1_para_cargar.xlsx como consolidado general.
Sube los archivos 07 a 10 en su nivel correspondiente.

El resultado debe conservar Prueba 1, añadir Prueba 2 y recalcular Nota_Total.
Si vuelves a subir archivos de Prueba 1, la aplicación debe bloquear el proceso
para no sobrescribir las notas existentes.
""",
        encoding="utf-8",
    )
    second_test_files.append(second_instructions)
    second_zip = OUTPUT / "ejemplo_acumulacion_prueba_2.zip"
    with ZipFile(second_zip, "w", compression=ZIP_DEFLATED) as archive:
        for path in second_test_files:
            archive.write(path, arcname=path.name)

    print(f"Archivos de prueba creados en: {OUTPUT}")
    print(f"Paquete: {zip_path}")
    print(f"Paquete acumulativo: {second_zip}")


if __name__ == "__main__":
    main()
