import unittest
from bs4 import BeautifulSoup

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from parsers import (
    extract_subjects_from_card_blocks,
    compute_curriculum_total_ects,
    is_spurious_or_administrative_subject
)
from univ_web_crawler import is_same_or_subdomain, extract_html_subjects

class TestCardBlocksAndSubdomains(unittest.TestCase):
    
    def test_is_same_or_subdomain_institutional_apps(self):
        """Verifica que los subdominios de portales de gestión institucional sean reconocidos como válidos."""
        # UJI
        self.assertTrue(is_same_or_subdomain("https://ujiapps.uji.es/sia/rest/publicacion/estudio/259", "https://www.uji.es"))
        self.assertTrue(is_same_or_subdomain("http://sia.uji.es/pls/sia", "https://www.uji.es"))
        
        # UAM
        self.assertTrue(is_same_or_subdomain("https://secretaria.uam.es/estudios", "https://www.uam.es"))
        
        # Uniovi
        self.assertTrue(is_same_or_subdomain("https://sies.uniovi.es/servicios/guias", "https://www.uniovi.es"))
        
        # Dominio externo diferente (no debe ser subdominio)
        self.assertFalse(is_same_or_subdomain("https://www.elmundo.es/noticia", "https://www.uji.es"))
        self.assertFalse(is_same_or_subdomain("https://www.google.com", "https://www.uam.es"))

    def test_extract_subjects_from_card_blocks(self):
        """Verifica la extracción de asignaturas desde bloques/tarjetas de texto estructurado de aplicaciones web."""
        sample_card_text = """
        CA2501 - COMUNICACIÓ ORAL I ESCRITA (ESPANYOL)
        Curs 1 - Semestre 1 - Formació Bàsica
        6	60	90
        CRÈDITS	HORES PRESENCIALS	HORES NO PRESENCIALS
        Mostra detalls

        CA2502 - COMUNICACIÓ ORAL I ESCRITA (CATALÀ)
        Curs 1 - Semestre 1 - Formació Bàsica
        6	60	90
        CRÈDITS	HORES PRESENCIALS	HORES NO PRESENCIALS
        Mostra detalls

        CA2503 - TEORIA DE LA IMATGE
        Curs 1 - Semestre 1 - Formació Bàsica
        6	60	90
        CRÈDITS	HORES PRESENCIALS	HORES NO PRESENCIALS
        Mostra detalls

        CA2506 - TEORIA I TÈCNICA DE LA FOTOGRAFIA
        Curs 1 - Semestre 1 - Obligatòria
        6	60	90
        CRÈDITS	HORES PRESENCIALS	HORES NO PRESENCIALS
        Mostra detalls
        """
        
        elems = extract_subjects_from_card_blocks(sample_card_text)
        self.assertEqual(len(elems), 4)
        
        # Asignatura 1
        self.assertEqual(elems[0]["codigo_asignatura"], "CA2501")
        self.assertEqual(elems[0]["nombre_elemento"], "COMUNICACIÓ ORAL I ESCRITA (ESPANYOL)")
        self.assertEqual(elems[0]["creditos_ects"], "6")
        self.assertEqual(elems[0]["caracter"], "FB")
        self.assertEqual(elems[0]["curso"], "1")
        self.assertEqual(elems[0]["cuatrimestre"], "1C")
        
        # Asignatura 4
        self.assertEqual(elems[3]["codigo_asignatura"], "CA2506")
        self.assertEqual(elems[3]["nombre_elemento"], "TEORIA I TÈCNICA DE LA FOTOGRAFIA")
        self.assertEqual(elems[3]["creditos_ects"], "6")
        self.assertEqual(elems[3]["caracter"], "OB")
        self.assertEqual(elems[3]["curso"], "1")
        self.assertEqual(elems[3]["cuatrimestre"], "1C")

    def test_extract_html_subjects_card_fallback(self):
        """Verifica que extract_html_subjects recurra automáticamente a tarjetas cuando no hay etiquetas <table>."""
        html_without_table = """
        <div class="main-content">
            <h2>Pla d'Estudis</h2>
            <div class="card-item">
                <p>20501 - Fundamentos de Programación</p>
                <p>Curso 1 - Semestre 1 - Formación Básica</p>
                <p>6 Créditos ECTS</p>
            </div>
            <div class="card-item">
                <p>20502 - Álgebra Lineal y Geometría</p>
                <p>Curso 1 - Semestre 1 - Formación Básica</p>
                <p>6 Créditos ECTS</p>
            </div>
            <div class="card-item">
                <p>20503 - Estructuras de Datos y Algoritmos</p>
                <p>Curso 1 - Semestre 2 - Obligatoria</p>
                <p>6 Créditos ECTS</p>
            </div>
        </div>
        """
        soup = BeautifulSoup(html_without_table, "html.parser")
        elems = extract_html_subjects(soup)
        self.assertEqual(len(elems), 3)
        self.assertEqual(elems[0]["codigo_asignatura"], "20501")
        self.assertEqual(elems[0]["nombre_elemento"], "Fundamentos de Programación")
        self.assertEqual(elems[0]["creditos_ects"], "6")

if __name__ == "__main__":
    unittest.main()
