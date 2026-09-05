import unittest

from parsers.boe_pdf import _extract_rows_from_positioned_lines


class BoeLegacyRowTests(unittest.TestCase):
    def test_reconstructs_course_first_rows_when_pdf_splits_header(self):
        lines = [
            "Materia Curso Carácter Período",
            "Cr_ Org_",
            "ects temporal",
            "Anatomía Funcional . . . . . . . . 1 BA 1 6 Semestral.",
            "Teoría e Historia de la Danza................... 1 BA 1 ó 2 6 Semestral.",
            "Música Aplicada al Movimiento ................. 2 2 3 Semestral.",
        ]
        elements = _extract_rows_from_positioned_lines(lines)
        self.assertEqual(
            ["Anatomía Funcional", "Teoría e Historia de la Danza", "Música Aplicada al Movimiento"],
            [item["nombre_elemento"] for item in elements],
        )
        self.assertEqual([6.0, 6.0, 3.0], [item["creditos_ects"] for item in elements])
        self.assertEqual(["1", "1", "2"], [item["curso"] for item in elements])


if __name__ == "__main__":
    unittest.main()
