import os
import sys
import unittest

from pydantic import ValidationError


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "API")))
from schemas.schemas import ElementoCurricularCreate, TitulacionCreate


class TestApiNumericValidation(unittest.TestCase):
    def test_degree_prices_must_be_finite_and_non_negative(self):
        base = {"codigo_estudio": "2500001", "titulo": "Grado de prueba", "universidad_codigo": "001"}
        for invalid in (-1, float("nan"), float("inf"), 10000):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                TitulacionCreate(**base, precio_credito_ects=invalid)

    def test_subject_numeric_details_must_fit_database_range(self):
        for field, invalid in (("creditos_teoria", -0.5), ("creditos_practica", float("inf")), ("calificacion_minima", 100)):
            with self.subTest(field=field, invalid=invalid), self.assertRaises(ValidationError):
                ElementoCurricularCreate(nombre_elemento="Asignatura", **{field: invalid})

    def test_valid_prices_are_preserved(self):
        degree = TitulacionCreate(
            codigo_estudio="2500001", titulo="Grado de prueba", universidad_codigo="001", precio_credito_ects=12.62
        )
        self.assertEqual(degree.precio_credito_ects, 12.62)


if __name__ == "__main__":
    unittest.main()
