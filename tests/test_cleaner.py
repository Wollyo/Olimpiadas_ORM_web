import unittest

import pandas as pd

from src.cleaner import Cleaner, detect_columns, detect_problems
from src.matcher import find_column


class CleanerTests(unittest.TestCase):
    def base_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Numero identificacion": ["1234567"],
                "Nombres": ["Ángela"],
                "Apellidos": ["Pérez"],
                "Nombre del colegio o institución educativa": ["ie gabo"],
                "Departamento": ["valle"],
                "Municipio": ["santiago de cali"],
                "Nivel (junio,basico, medio o avanzado)": ["Básico"],
                "Grado": ["7°"],
                "Sector": ["Oficial"],
                "Genero": ["F"],
            }
        )

    def test_preserves_grade_and_normalizes_level(self):
        cleaned, _ = Cleaner.prepare(self.base_frame())

        self.assertEqual(cleaned.loc[0, "Grado"], "7")
        self.assertEqual(cleaned.loc[0, "Nivel"], "Básico")
        self.assertEqual(cleaned.loc[0, "Nombres"], "ÁNGELA")
        self.assertEqual(cleaned.loc[0, "Departamento"], "Valle del Cauca")
        self.assertEqual(cleaned.loc[0, "Municipio"], "Cali")
        self.assertEqual(cleaned.loc[0, "tipo_colegio"], "Público")
        self.assertEqual(cleaned.loc[0, "genero_normalizado"], "Mujer")
        self.assertEqual(cleaned.loc[0, "Sector"], "Público")
        self.assertEqual(cleaned.loc[0, "Genero"], "Mujer")

    def test_normalizes_numeric_identification_separators(self):
        frame = self.base_frame()
        frame.loc[0, "Numero identificacion"] = "1.234-567"

        cleaned, _ = Cleaner.prepare(frame)

        self.assertEqual(cleaned.loc[0, "Numero identificacion"], "1234567")
        self.assertTrue(detect_problems(cleaned).empty)

    def test_does_not_turn_negative_monitor_id_into_student_id(self):
        frame = self.base_frame()
        frame.loc[0, "Numero identificacion"] = "-31"

        cleaned, _ = Cleaner.prepare(frame)
        problems = detect_problems(cleaned)

        self.assertEqual(cleaned.loc[0, "Numero identificacion"], "-31")
        self.assertIn("Identificación no numérica", problems.loc[0, "errores"])

    def test_infers_level_from_grade(self):
        frame = self.base_frame().drop(columns=["Nivel (junio,basico, medio o avanzado)"])
        frame["Grado"] = "10"

        cleaned, _ = Cleaner.prepare(frame)

        self.assertEqual(cleaned.loc[0, "Nivel"], "Avanzado")
        self.assertEqual(cleaned.loc[0, "Grado"], "10")

    def test_missing_location_columns_do_not_crash(self):
        frame = self.base_frame().drop(columns=["Departamento", "Municipio"])

        cleaned, detected = Cleaner.prepare(frame)

        self.assertEqual(cleaned.loc[0, "Departamento"], "")
        self.assertEqual(cleaned.loc[0, "Municipio"], "")
        self.assertEqual(detected.required_missing(), ["Departamento", "Municipio"])

    def test_detects_duplicates_and_invalid_ids(self):
        frame = pd.concat([self.base_frame()] * 3, ignore_index=True)
        frame.loc[2, "Numero identificacion"] = "ABC-123"
        cleaned, _ = Cleaner.prepare(frame)

        problems = detect_problems(cleaned)

        self.assertEqual(len(problems), 3)
        self.assertIn("Identificación duplicada", problems.loc[0, "errores"])
        self.assertIn("Identificación duplicada", problems.loc[1, "errores"])
        self.assertIn("Identificación no numérica", problems.loc[2, "errores"])
        self.assertEqual(problems.loc[0, "columnas_con_error"], "Numero identificacion")
        self.assertEqual(problems.loc[2, "columnas_con_error"], "Numero identificacion")

    def test_short_id_alias_does_not_match_surnames(self):
        columns = ["Nombres", "Apellidos", "Colegio"]

        self.assertIsNone(find_column(columns, ["ID"], allow_partial=True))
        self.assertIsNone(detect_columns(pd.DataFrame(columns=columns)).identification)

    def test_can_reprocess_an_exported_file(self):
        first_pass, _ = Cleaner.prepare(self.base_frame())

        second_pass, _ = Cleaner.prepare(first_pass)

        self.assertEqual(second_pass.loc[0, "Grado"], "7")
        self.assertEqual(second_pass.loc[0, "Nivel"], "Básico")
        self.assertEqual(second_pass.loc[0, "_fila_origen"], 2)


if __name__ == "__main__":
    unittest.main()

