"""Pruebas unitarias para la ampliación del catálogo de honorarios en universidades privadas."""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from lexicon.pricing_tables import OFFICIAL_PRIVATE_UNIVERSITIES_PRICES_CATALOG


class TestPrivatePricingCatalogExpansion(unittest.TestCase):
    """Verifica que el catálogo cubra las universidades privadas identificadas."""

    REQUIRED_CODES = [
        "041",  # Ramon Llull
        "055",  # Ramon Llull alias
        "060",  # UVic-UCC
        "068",  # Francisco de Vitoria
        "064",  # Francisco de Vitoria alias
        "032",  # Pontificia de Salamanca
        "062",  # UIC Barcelona
        "082",  # Europea de Valencia
        "069",  # UEMC
        "059",  # UCAV
        "073",  # San Jorge
        "088",  # Villanueva
        "030",  # Deusto
        "031",  # Navarra
        "033",  # Comillas
        "053",  # Europea de Madrid (RUCT)
        "100",  # UDIT
    ]

    def test_all_required_private_institutions_present(self):
        for code in self.REQUIRED_CODES:
            self.assertIn(
                code,
                OFFICIAL_PRIVATE_UNIVERSITIES_PRICES_CATALOG,
                f"Código {code} debe estar presente en OFFICIAL_PRIVATE_UNIVERSITIES_PRICES_CATALOG",
            )

    def test_pricing_values_are_academically_plausible(self):
        for code in self.REQUIRED_CODES:
            entry = OFFICIAL_PRIVATE_UNIVERSITIES_PRICES_CATALOG[code]
            self.assertIn("nombre", entry)
            self.assertIn("Grado", entry)
            self.assertIn("Máster", entry)
            self.assertIn("Doctorado", entry)

            grado_cred = entry["Grado"]["precio_credito_ects"]
            master_cred = entry["Máster"]["precio_credito_ects"]
            doc_anual = entry["Doctorado"]["precio_estimado_anual"]

            # Los créditos en universidades privadas en España oscilan entre 60 y 600 €/ECTS
            self.assertTrue(50.0 <= grado_cred <= 600.0, f"Grado {code}: {grado_cred} fuera de rango")
            self.assertTrue(60.0 <= master_cred <= 800.0, f"Máster {code}: {master_cred} fuera de rango")
            self.assertTrue(200.0 <= doc_anual <= 2000.0, f"Doctorado {code}: {doc_anual} fuera de rango")


if __name__ == "__main__":
    unittest.main()
