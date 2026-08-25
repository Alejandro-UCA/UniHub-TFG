import unittest
from bs4 import BeautifulSoup
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from univ_web_crawler import (
    is_spider_trap_or_spurious_url,
    is_dynamic_academic_hub,
    extract_breadcrumb_parent_hubs,
    extract_hydration_payload_degrees,
    extract_form_select_academic_options,
    extract_js_event_links
)


class TestDynamicHubDiscovery(unittest.TestCase):
    """
    Pruebas unitarias para el Motor Autónomo de Descubrimiento de HUBs Curriculares (6 Capas).
    Verifica que el sistema descubre y navega catálogos sin depender de diccionarios de palabras fijas.
    """

    def test_spider_trap_rejection(self):
        """Descarta calendarios, eventos, noticias y enlaces no curriculares."""
        self.assertTrue(is_spider_trap_or_spurious_url("https://www.uca.es/agenda/2026/08/evento-1", "Evento"))
        self.assertTrue(is_spider_trap_or_spurious_url("https://www.upc.edu/noticias/inauguracion", "Noticia"))
        self.assertTrue(is_spider_trap_or_spurious_url("https://www.uv.es/portal/calendario?month=10&year=2026", "Calendario"))
        self.assertTrue(is_spider_trap_or_spurious_url("https://www.uah.es/aviso-legal", "Aviso Legal"))
        self.assertTrue(is_spider_trap_or_spurious_url("https://www.us.es/login", "Acceso"))
        
        # Enlace curricular válido NO es spider trap
        self.assertFalse(is_spider_trap_or_spurious_url("https://www.uca.es/titulacion/grado-en-ingenieria-informatica", "Grado en Ingeniería Informática"))
        self.assertFalse(is_spider_trap_or_spurious_url("https://www.fib.upc.edu/estudis/graus/grau-en-enginyeria-informatica", "Grau en Enginyeria Informàtica"))

    def test_dom_navigation_landmark_hub(self):
        """Capa 1: Detección de HUBs dentro de <nav> y <header> sin palabras prefijadas."""
        html = """
        <html>
            <body>
                <nav class="site-nav">
                    <ul>
                        <li><a href="/curriculos/todos">Academic Programs 2026</a></li>
                        <li><a href="/contacto">Contacto</a></li>
                    </ul>
                </nav>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        a_hub = soup.find("a", href="/curriculos/todos")
        self.assertTrue(is_dynamic_academic_hub(soup, a_hub, "https://www.univ.es/curriculos/todos", "https://www.univ.es"))

    def test_sibling_uniformity_hub_without_keywords(self):
        """Capa 2: Detección por densidad de enlaces hermanos homogéneos (Sibling Uniformity >= 6)."""
        html = """
        <div class="main-catalog-grid">
            <a href="/programme/CS101">Computer Science Engineering</a>
            <a href="/programme/EE102">Electrical Engineering Degree</a>
            <a href="/programme/ME103">Mechanical Engineering Degree</a>
            <a href="/programme/BT104">Biotechnology and Biosystems</a>
            <a href="/programme/BA105">Business Administration Degree</a>
            <a href="/programme/LW106">International Law and Economics</a>
            <a href="/programme/MD107">General Medicine and Surgery</a>
            <a href="/programme/PH108">Pharmacy and Clinical Analysis</a>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        first_a = soup.find("a", href="/programme/CS101")
        # Debe detectarse como HUB o contenedor de catálogo válido por densidad de hermanos
        self.assertTrue(is_dynamic_academic_hub(soup, first_a, "https://www.univ.es/programme/CS101", "https://www.univ.es"))

    def test_breadcrumb_hierarchical_ascendance(self):
        """Capa 3: Ascenso jerárquico por migas de pan para descubrir portales padre."""
        html = """
        <ol class="breadcrumb">
            <li><a href="/">Inicio</a></li>
            <li><a href="/facultades/escuela-ingenieria">Escuela de Ingeniería</a></li>
            <li><a href="/facultades/escuela-ingenieria/oferta">Oferta Curricular</a></li>
            <li class="active">Grado en Informática</li>
        </ol>
        """
        soup = BeautifulSoup(html, "html.parser")
        hubs = extract_breadcrumb_parent_hubs(soup, "https://www.univ.es/facultades/escuela-ingenieria/oferta/grado-informatica", "https://www.univ.es")
        self.assertIn("https://www.univ.es/facultades/escuela-ingenieria", hubs)
        self.assertIn("https://www.univ.es/facultades/escuela-ingenieria/oferta", hubs)

    def test_hydration_payload_extraction(self):
        """Capa 4: Extracción desde JSON-LD (Schema.org) y Next.js __NEXT_DATA__."""
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "ItemList",
                    "itemListElement": [
                        { "@type": "Course", "name": "Grado en Biotecnología", "url": "/estudios/biotecnologia" },
                        { "@type": "Course", "name": "Grado en Matemáticas", "url": "/estudios/matematicas" }
                    ]
                }
                </script>
                <script id="__NEXT_DATA__" type="application/json">
                {
                    "props": {
                        "pageProps": {
                            "degrees": [
                                { "title": "Grado en Enfermería", "slug": "/estudios/enfermeria" },
                                { "title": "Grado en Fisioterapia", "slug": "/estudios/fisioterapia" }
                            ]
                        }
                    }
                }
                </script>
            </head>
            <body></body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        payloads = extract_hydration_payload_degrees(soup, "https://www.univ.es")
        titles = [p[1] for p in payloads]
        urls = [p[0] for p in payloads]
        
        self.assertIn("Grado en Biotecnología", titles)
        self.assertIn("Grado en Matemáticas", titles)
        self.assertIn("Grado en Enfermería", titles)
        self.assertIn("Grado en Fisioterapia", titles)
        self.assertIn("https://www.univ.es/estudios/biotecnologia", urls)
        self.assertIn("https://www.univ.es/estudios/enfermeria", urls)

    def test_form_select_option_harvesting(self):
        """Capa 5: Extracción de desplegables de formularios interactivos."""
        html = """
        <form action="/consulta/planes" method="GET">
            <select name="cod_plan" id="selector_carreras">
                <option value="">Seleccione titulación...</option>
                <option value="G101">Grado en Ingeniería Mecánica</option>
                <option value="G102">Grado en Ingeniería Eléctrica</option>
                <option value="G103">Grado en Ingeniería Química</option>
                <option value="G104">Grado en Ingeniería Electrónica</option>
                <option value="G105">Grado en Ingeniería Informática</option>
                <option value="G106">Grado en Diseño Industrial</option>
            </select>
        </form>
        """
        soup = BeautifulSoup(html, "html.parser")
        opts = extract_form_select_academic_options(soup, "https://www.univ.es/consulta")
        self.assertEqual(len(opts), 6)
        self.assertEqual(opts[0][1], "Grado en Ingeniería Mecánica")
        self.assertIn("cod_plan=G101", opts[0][0])
        self.assertIn("cod_plan=G105", opts[4][0])

    def test_js_event_deobfuscation(self):
        """Capa 6: Desofuscación de onclick y data-url."""
        html = """
        <div>
            <button onclick="location.href='/estudios/grado-fisica'">Grado en Física</button>
            <div data-url="/estudios/grado-quimica">Grado en Química</div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        js_links = extract_js_event_links(soup, "https://www.univ.es")
        urls = [item[0] for item in js_links]
        self.assertIn("https://www.univ.es/estudios/grado-fisica", urls)
        self.assertIn("https://www.univ.es/estudios/grado-quimica", urls)


if __name__ == "__main__":
    unittest.main()
