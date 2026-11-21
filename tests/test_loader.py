import unittest

from src.loader import DataLoadError, DataLoader


class DataLoaderTests(unittest.TestCase):
    def test_reads_semicolon_csv_and_keeps_leading_zero(self):
        content = "Identificacion;Nombres\n00123456;Ana\n".encode("utf-8")

        frame = DataLoader.from_bytes("inscripciones.csv", content)

        self.assertEqual(frame.loc[0, "Identificacion"], "00123456")
        self.assertEqual(frame.loc[0, "Nombres"], "Ana")

    def test_reads_cp1252_csv(self):
        content = "Identificación,Nombres\n123456,Ángela\n".encode("cp1252")

        frame = DataLoader.from_bytes("inscripciones.csv", content)

        self.assertEqual(frame.loc[0, "Nombres"], "Ángela")

    def test_makes_headers_unique_after_trimming_spaces(self):
        content = "Colegio,Colegio \nUno,Dos\n".encode("utf-8")

        frame = DataLoader.from_bytes("inscripciones.csv", content)

        self.assertEqual(frame.columns.tolist(), ["Colegio", "Colegio (2)"])
        self.assertEqual(frame.loc[0, "Colegio"], "Uno")
        self.assertEqual(frame.loc[0, "Colegio (2)"], "Dos")

    def test_rejects_unknown_extension(self):
        with self.assertRaises(DataLoadError):
            DataLoader.from_bytes("inscripciones.txt", b"dato")


if __name__ == "__main__":
    unittest.main()
