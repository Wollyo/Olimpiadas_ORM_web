import unittest

import pandas as pd

from src.cleaner import Cleaner
from src.results_merger import (
    GradeFileError,
    build_results_export,
    combine_grade_files,
    merge_with_registrations,
    prepare_grade_file,
)


class ResultsMergerTests(unittest.TestCase):
    def grade_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Número de ID": ["1234567", "7654321"],
                "Calificación/80": ["72,50", "60.00"],
                "Estado": ["Finalizado", "Finalizado"],
            }
        )

    def registration_frame(self) -> pd.DataFrame:
        source = pd.DataFrame(
            {
                "Numero identificacion": ["1234567", "7654321", "9999999"],
                "Nombres": ["Ana", "Luis", "Sara"],
                "Apellidos": ["Uno", "Dos", "Tres"],
                "Nombre del colegio o institución educativa": ["A", "B", "C"],
                "Departamento": ["Valle", "Valle", "Cauca"],
                "Municipio": ["Cali", "Cali", "Popayán"],
                "Nivel": ["Junior", "Junior", "Básico"],
                "Grado": ["4", "5", "6"],
            }
        )
        return Cleaner.prepare(source)[0]

    def test_prepares_moodle_grade_file(self):
        prepared = prepare_grade_file(
            self.grade_frame(),
            level="Junior",
            file_name="ORM-Prueba #1-Junior.csv",
        )

        self.assertEqual(prepared.test_name, "Prueba 1")
        self.assertEqual(prepared.maximum_score, 80)
        self.assertEqual(prepared.frame.loc[0, "Nota de la prueba"], 72.5)
        self.assertAlmostEqual(prepared.frame.loc[0, "Porcentaje de la prueba"], 90.62)

    def test_keeps_highest_duplicate_attempt_and_reports_the_other(self):
        frame = self.grade_frame()
        frame.loc[1, "Número de ID"] = "1234567"

        prepared = prepare_grade_file(frame, level="Junior", file_name="Prueba 1.csv")

        self.assertEqual(len(prepared.frame), 1)
        self.assertEqual(prepared.frame.iloc[0]["Nota de la prueba"], 72.5)
        self.assertEqual(len(prepared.excluded_rows), 1)
        self.assertIn(
            "Intento duplicado",
            prepared.excluded_rows.iloc[0]["Motivo de exclusión"],
        )

    def test_excludes_negative_monitor_id_without_blocking_students(self):
        frame = self.grade_frame()
        monitor = pd.DataFrame(
            {
                "Número de ID": ["-31"],
                "Calificación/80": ["80"],
                "Estado": ["Finalizado"],
            }
        )
        frame = pd.concat([frame, monitor], ignore_index=True).fillna("")

        prepared = prepare_grade_file(frame, level="Junior", file_name="Prueba #1.csv")

        self.assertEqual(len(prepared.frame), 2)
        self.assertEqual(len(prepared.excluded_rows), 1)
        self.assertEqual(prepared.excluded_rows.iloc[0]["Número de ID"], "-31")
        self.assertIn(
            "posible monitor o profesor",
            prepared.excluded_rows.iloc[0]["Motivo de exclusión"],
        )

    def test_converts_moodle_dash_to_zero_without_excluding_the_student(self):
        frame = self.grade_frame()
        frame.loc[0, "Calificación/80"] = "-"

        prepared = prepare_grade_file(frame, level="Junior", file_name="Prueba #1.csv")
        grades, _ = combine_grade_files([prepared])
        merged, _, _ = merge_with_registrations(self.registration_frame(), grades)
        student = merged[merged["Numero identificacion"] == "1234567"].iloc[0]

        self.assertEqual(len(prepared.excluded_rows), 0)
        self.assertEqual(student["Nota de la prueba"], 0)
        self.assertFalse(student["Presentó la prueba"])
        self.assertEqual(
            student["Estado de presentación"],
            "Sin calificación / no presentó",
        )

    def test_ignores_moodle_summary_row(self):
        frame = self.grade_frame()
        summary = pd.DataFrame(
            {
                "Número de ID": [""],
                "Calificación/80": ["65"],
                "Estado": [""],
                "Apellido(s)": ["Promedio general"],
            }
        )
        frame = pd.concat([frame, summary], ignore_index=True).fillna("")

        prepared = prepare_grade_file(
            frame,
            level="Junior",
            file_name="Prueba #1 Junior.csv",
        )

        self.assertEqual(len(prepared.frame), 2)
        self.assertEqual(prepared.administrative_rows, 1)

    def test_merges_by_id_and_keeps_students_without_grade(self):
        prepared = prepare_grade_file(
            self.grade_frame(),
            level="Junior",
            file_name="Prueba #1 Junior.csv",
        )
        grades, test_name = combine_grade_files([prepared])

        merged, unmatched, mismatches = merge_with_registrations(
            self.registration_frame(), grades
        )

        self.assertEqual(test_name, "Prueba 1")
        self.assertEqual(len(merged), 3)
        self.assertEqual(int(merged["Presentó la prueba"].sum()), 2)
        absent = merged[merged["Numero identificacion"] == "9999999"].iloc[0]
        self.assertEqual(absent["Nota de la prueba"], 0)
        self.assertEqual(absent["Porcentaje de la prueba"], 0)
        self.assertEqual(
            absent["Estado de presentación"],
            "Sin calificación / no presentó",
        )
        self.assertTrue(unmatched.empty)
        self.assertTrue(mismatches.empty)

    def test_compact_export_preserves_previous_tests_and_recalculates_total(self):
        registrations = self.registration_frame()
        registrations["Prueba 1"] = [50, 60, 0]
        prepared = prepare_grade_file(
            self.grade_frame(),
            level="Junior",
            file_name="Prueba #2 Junior.csv",
        )
        grades, test_name = combine_grade_files([prepared])
        merged, _, _ = merge_with_registrations(registrations, grades)

        result = build_results_export(merged, test_name)

        self.assertEqual(
            result.columns.tolist(),
            [
                "Número de ID",
                "Nombre",
                "Apellido(s)",
                "Correo electrónico",
                "Nivel",
                "Grado",
                "Codigo ORM",
                "Colegio",
                "Departamento",
                "Ciudad",
                "Prueba 1",
                "Prueba 2",
                "Nota_Total",
            ],
        )
        self.assertEqual(result.loc[0, "Prueba 1"], 50)
        self.assertEqual(result.loc[0, "Prueba 2"], 72.5)
        self.assertEqual(result.loc[0, "Nota_Total"], 122.5)
        self.assertEqual(result.loc[2, "Prueba 2"], 0)

    def test_does_not_overwrite_existing_test(self):
        registrations = self.registration_frame()
        registrations["Prueba 1"] = [50, 60, 0]
        prepared = prepare_grade_file(
            self.grade_frame(),
            level="Junior",
            file_name="Prueba #1 Junior.csv",
        )
        grades, test_name = combine_grade_files([prepared])
        merged, _, _ = merge_with_registrations(registrations, grades)

        with self.assertRaises(GradeFileError):
            build_results_export(merged, test_name)


if __name__ == "__main__":
    unittest.main()
