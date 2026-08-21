import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from precios_crawler import (
    compute_degree_price,
    is_public_university,
    apply_price_info_to_degree,
    normalize_ccaa_name
)

class TestPhase1Part3Strict(unittest.TestCase):

    def test_01_unknown_ccaa_returns_none_and_does_not_assume_andalucia(self):
        """Verifica que una CCAA desconocida o vacía NO asuma Andalucía ni precios inventados."""
        res_empty = compute_degree_price(
            ccaa="",
            tipo_univ="Pública",
            nivel_academico="Grado",
            titulo="Grado en Matemáticas"
        )
        self.assertIsNone(res_empty["precio_credito_ects"])
        self.assertIsNone(res_empty["precio_estimado_anual"])
        self.assertIn("CCAA desconocida", res_empty["fuente_precio"])

        res_unknown = compute_degree_price(
            ccaa="Región Fantasma",
            tipo_univ="Pública",
            nivel_academico="Grado",
            titulo="Grado en Matemáticas"
        )
        self.assertIsNone(res_unknown["precio_credito_ects"])
        self.assertIsNone(res_unknown["precio_estimado_anual"])
        self.assertIn("CCAA desconocida", res_unknown["fuente_precio"])

    def test_02_private_university_returns_none_for_public_tariffs(self):
        """Verifica que las universidades privadas no reciban tarifas públicas por defecto."""
        res = compute_degree_price(
            ccaa="Comunidad de Madrid",
            tipo_univ="Privada",
            nivel_academico="Grado",
            titulo="Grado en ADE"
        )
        self.assertIsNone(res["precio_credito_ects"])
        self.assertIsNone(res["precio_credito_2"])
        self.assertIsNone(res["precio_credito_3"])
        self.assertIsNone(res["precio_credito_4"])
        self.assertIsNone(res["precio_estimado_anual"])
        self.assertIn("Privada", res["fuente_precio"])

    def test_03_official_andalucia_siiu_prices(self):
        """Verifica los precios exactos del Decreto Oficial de Andalucía (sin multiplicadores inventados)."""
        res = compute_degree_price(
            ccaa="Andalucía",
            tipo_univ="Pública",
            nivel_academico="Grado",
            titulo="Grado en Ingeniería Informática"
        )
        self.assertEqual(res["precio_credito_ects"], 12.62)
        self.assertEqual(res["precio_credito_2"], 25.24)
        self.assertEqual(res["precio_credito_3"], 54.40)
        self.assertEqual(res["precio_credito_4"], 75.60)
        # 60 * 12.62 + 59.10 = 757.2 + 59.10 = 816.30
        self.assertEqual(res["precio_estimado_anual"], 816.30)
        self.assertIn("Andalucía", res["fuente_precio"])

    def test_04_official_madrid_siiu_prices(self):
        """Verifica los precios exactos del Decreto Oficial de la Comunidad de Madrid."""
        res = compute_degree_price(
            ccaa="Madrid",
            tipo_univ="Pública",
            nivel_academico="Grado",
            titulo="Grado en Derecho"
        )
        self.assertEqual(res["precio_credito_ects"], 21.39)
        self.assertEqual(res["precio_credito_2"], 36.36)
        self.assertEqual(res["precio_credito_3"], 78.44)
        self.assertEqual(res["precio_credito_4"], 108.94)
        # 60 * 21.39 + 65.00 = 1283.4 + 65.00 = 1348.40
        self.assertEqual(res["precio_estimado_anual"], 1348.40)

    def test_05_official_cataluna_master_prices(self):
        """Verifica los precios de Máster Habilitante vs No Habilitante en Cataluña."""
        res_hab = compute_degree_price(
            ccaa="Cataluña",
            tipo_univ="Pública",
            nivel_academico="Máster Universitario",
            titulo="Máster Universitario en Abogacía"
        )
        self.assertEqual(res_hab["precio_credito_ects"], 27.67)

        res_no_hab = compute_degree_price(
            ccaa="Cataluña",
            tipo_univ="Pública",
            nivel_academico="Máster Universitario",
            titulo="Máster Universitario en Inteligencia Artificial"
        )
        self.assertEqual(res_no_hab["precio_credito_ects"], 41.17)

    def test_06_is_public_university_logic(self):
        """Verifica la función pura is_public_university con acentos y variaciones."""
        self.assertTrue(is_public_university("Pública"))
        self.assertTrue(is_public_university("publica"))
        self.assertTrue(is_public_university("Universidad Pública"))
        self.assertFalse(is_public_university("Privada"))
        self.assertFalse(is_public_university("Universidad de la Iglesia"))
        self.assertFalse(is_public_university(""))
        self.assertFalse(is_public_university(None))

    def test_07_apply_price_info_to_degree(self):
        """Verifica la asignación uniforme de precios ECTS a diccionarios de grado."""
        deg_pub = {"titulo": "Grado en Física"}
        price_info_pub = {
            "precio_credito_ects": 15.10,
            "precio_credito_2": 25.67,
            "precio_credito_3": 55.37,
            "precio_credito_4": 76.90,
            "precio_estimado_anual": 952.00,
            "fuente_precio": "Oficial SIIU / Decret Valencia"
        }
        apply_price_info_to_degree(deg_pub, price_info_pub, "Pública")
        self.assertEqual(deg_pub["precio_credito_ects"], 15.10)
        self.assertEqual(deg_pub["precio_credito_2"], 25.67)
        self.assertEqual(deg_pub["fuente_precio"], "Oficial SIIU / Decret Valencia")

        deg_priv = {"titulo": "Grado en Bioquímica"}
        apply_price_info_to_degree(deg_priv, {}, "Privada")
        self.assertNotIn("precio_credito_ects", deg_priv)
        self.assertIn("Privada", deg_priv["fuente_precio"])

    def test_08_normalize_ccaa_name_empty(self):
        """Verifica que normalize_ccaa_name no invente Andalucía para cadenas vacías."""
        self.assertEqual(normalize_ccaa_name(""), "")
        self.assertEqual(normalize_ccaa_name(None), "")
        self.assertEqual(normalize_ccaa_name("Andalucía"), "Andalucía")
        self.assertEqual(normalize_ccaa_name("Euskadi"), "País Vasco")

if __name__ == "__main__":
    unittest.main(verbosity=2)
