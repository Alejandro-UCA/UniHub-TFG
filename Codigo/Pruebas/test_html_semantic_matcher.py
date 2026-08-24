import unittest
import sys
import os
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath('Codigo/Crawler'))

from univ_web_crawler import is_html_page_matching_degree
from parsers import is_section_matching, extract_degree_core_keywords

class TestHTMLSemanticMatcher(unittest.TestCase):

    def test_reject_cross_degree_sitemap_collision(self):
        target_title = "Máster Universitario en Materiales Complejos: Análisis Térmico y Caracterización Estructural"
        univ_name = "Universitat Autònoma de Barcelona"

        html_mismatch = """
        <html>
        <head><title>Màster Universitari en Ecologia Terrestre i Gestió de la Biodiversitat - UAB Barcelona</title></head>
        <body>
          <h1>Ecologia Terrestre i Gestió de la Biodiversitat</h1>
          <h2>Pla d'estudis</h2>
          <table>
            <tr><td>Ecologia de Poblacions</td><td>6 ECTS</td></tr>
            <tr><td>Gestió de la Biodiversitat</td><td>6 ECTS</td></tr>
          </table>
        </body>
        </html>
        """
        soup_mismatch = BeautifulSoup(html_mismatch, "html.parser")
        matched = is_html_page_matching_degree(
            soup_mismatch, 
            target_title, 
            univ_name, 
            "https://www.uab.cat/web/estudiar/l-oferta-de-masters-oficials/matricula/ecologia-terrestre-i-gestio-de-la-biodiversitat-1345655869231.html"
        )
        self.assertFalse(matched, "Should strictly reject mismatched cross-degree HTML page")

    def test_accept_genuine_degree_page_multilingual(self):
        target_title = "Máster Universitario en Materiales Complejos: Análisis Térmico y Caracterización Estructural"
        univ_name = "Universitat Autònoma de Barcelona"

        html_catalan = """
        <html>
        <head><title>Màster Universitari en Materials Complexos - UAB</title></head>
        <body>
          <h1>Materials Complexos: Anàlisi Tèrmica i Caracterització Estructural</h1>
          <h2>Pla d'estudis</h2>
          <table>
            <tr><td>Anàlisi Tèrmica Avançada</td><td>6 ECTS</td></tr>
            <tr><td>Difracció de Raigs X</td><td>6 ECTS</td></tr>
          </table>
        </body>
        </html>
        """
        soup_catalan = BeautifulSoup(html_catalan, "html.parser")
        matched = is_html_page_matching_degree(
            soup_catalan, 
            target_title, 
            univ_name, 
            "https://www.uab.cat/web/estudiar/materials-complexos-1345655869231.html"
        )
        self.assertTrue(matched, "Should accept genuine multilingual degree match")

    def test_reject_academic_level_collision_grado_vs_master(self):
        target_title = "Graduado o Graduada en Inteligencia Artificial / Bachelor in Artificial Intelligence"
        univ_name = "Universitat Autònoma de Barcelona"

        html_master = """
        <html>
        <head><title>Màster en Intel·ligència Artificial i Big Data en Salut - UAB</title></head>
        <body>
          <h1>Màster en Intel·ligència Artificial i Big Data en Salut</h1>
          <table><tr><td>Assignatura 1</td><td>6 ECTS</td></tr></table>
        </body>
        </html>
        """
        soup_master = BeautifulSoup(html_master, "html.parser")
        matched = is_html_page_matching_degree(
            soup_master,
            target_title,
            univ_name,
            "https://www.uab.cat/web/postgrau/master-en-intel-ligencia-artificial-i-big-data-en-salut/pla-d-estudis-1203328492980.html/param1-4291_ca/"
        )
        self.assertFalse(matched, "Should reject master/postgrau page when searching for a Bachelor degree")

    def test_reject_extension_course_page(self):
        target_title = "Graduado o Graduada en Ingeniería Química por la Universidad de Alcalá"
        univ_name = "Universidad de Alcalá"

        html_ext = """
        <html>
        <head><title>Precios Públicos Cursos de Extensión</title></head>
        <body><h1>Cursos de Extensión Universitaria</h1></body>
        </html>
        """
        soup_ext = BeautifulSoup(html_ext, "html.parser")
        matched = is_html_page_matching_degree(
            soup_ext,
            target_title,
            univ_name,
            "https://www.uah.es/export/sites/escuela-posgrado/es/extension-universitaria/.galleries/documentos/Precios-Publicos-Cursos-Extension-26-27.report.pdf"
        )
        self.assertFalse(matched, "Should reject non-official extension courses")

    def test_reject_disparate_degree_subjects(self):
        target_title = "Graduado o Graduada en Comunicación Audiovisual por la Universidad Autónoma de Barcelona"
        univ_name = "Universitat Autònoma de Barcelona"

        html_fq = """
        <html>
        <head><title>Grau de Física + Química - UAB</title></head>
        <body><h1>Grau de Física + Química</h1></body>
        </html>
        """
        soup_fq = BeautifulSoup(html_fq, "html.parser")
        matched = is_html_page_matching_degree(
            soup_fq,
            target_title,
            univ_name,
            "https://www.uab.cat/web/estudiar/llistat-de-graus/pla-d-estudis/pla-d-estudis-i-horaris/fisica-quimica-1345467811493.html"
        )
        self.assertFalse(matched, "Should reject Fisica + Quimica when searching for Comunicacion Audiovisual")


    def test_reject_teoria_politica_vs_asia_oriental(self):
        """Rechaza Grado en Estudios de Asia Oriental cuando se busca Máster en Teoría Política."""
        target_title = "Máster Universitario en Teoría Política y Cultura Democrática"
        univ_name = "Universitat Autònoma de Barcelona"
        page_url = "https://www.uab.cat/web/estudiar/llistat-de-graus/pla-d-estudis/pla-d-estudis-i-horaris/estudis-de-l-asia-oriental-1345467811493.html?param1=1223967776732"

        html_asia = """
        <html>
        <head><title>Grau en Estudis de l'Àsia Oriental - UAB Barcelona</title></head>
        <body><h1>Estudis de l'Àsia Oriental</h1></body>
        </html>
        """
        soup_asia = BeautifulSoup(html_asia, "html.parser")
        self.assertFalse(
            is_html_page_matching_degree(soup_asia, target_title, univ_name, page_url),
            "Debe rechazar Grado en Asia Oriental para Máster en Teoría Política"
        )

    def test_reject_ciencia_animal_vs_grado_fisica(self):
        """Rechaza Grado en Física cuando se busca Máster en Ciencia Animal."""
        target_title = "Máster Universitario en Investigación en Ciencia Animal y de la Tierra"
        univ_name = "Universidad de Alicante"
        page_url = "https://ciencias.ua.es/es/estudios/grados/fisica/modificacion-plan-de-estudios-grado-en-fisica.html"

        html_fisica = """
        <html>
        <head><title>Modificación Plan de Estudios Grado en Física - Facultad de Ciencias</title></head>
        <body><h1>Grado en Física</h1></body>
        </html>
        """
        soup_fisica = BeautifulSoup(html_fisica, "html.parser")
        self.assertFalse(
            is_html_page_matching_degree(soup_fisica, target_title, univ_name, page_url),
            "Debe rechazar Grado en Física para Máster en Ciencia Animal"
        )


    def test_reject_doctorado_literarios_vs_master_literatura(self):
        """Rechaza Máster en Literatura Comparada cuando se busca Doctorado en Estudios Literarios."""
        target_title = "Programa Oficial de Doctorado en Investigación en Estudios Literarios"
        univ_name = "Universitat Autònoma de Barcelona"
        page_url = "https://www.uab.cat/web/estudiar/l-oferta-de-masters-oficials/matricula/literatura-comparada-estudis-literaris-i-culturals-1345655869231.html"

        html_master = "<html><head><title>Màster en Literatura Comparada - UAB</title></head><body><h1>Màster Universitari en Literatura Comparada</h1></body></html>"
        soup_master = BeautifulSoup(html_master, "html.parser")
        self.assertFalse(
            is_html_page_matching_degree(soup_master, target_title, univ_name, page_url),
            "Debe rechazar Máster en Literatura para Doctorado"
        )

    def test_accept_logistica_uah_genuine_match(self):
        """Acepta el plan oficial del Máster en Logística de la UAH."""
        target_title = "Máster Universitario en Logística y Gestión de la Cadena de Suministro"
        univ_name = "Universidad de Alcalá"
        page_url = "https://posgrado.uah.es/es/masteres-universitarios/asignaturas/index.html?codPlan=M206"

        html_log = """
        <html>
        <head><title>Máster Universitario en Logística y Gestión de la Cadena de Suministro - UAH</title></head>
        <body>
          <h1>Máster Universitario en Logística y Gestión de la Cadena de Suministro</h1>
          <table>
            <tr><td>Gestión de Compras y Aprovisionamiento</td><td>6 ECTS</td></tr>
          </table>
        </body>
        </html>
        """
        soup_log = BeautifulSoup(html_log, "html.parser")
        self.assertTrue(
            is_html_page_matching_degree(soup_log, target_title, univ_name, page_url),
            "Debe aceptar el plan oficial de Logística de la UAH"
        )

    def test_reject_matematica_avanzada_vs_arritmologia(self):
        """Rechaza Arritmología Cardíaca Avanzada cuando se busca Matemática Avanzada."""
        target_title = "Máster Universitario en Matemática Avanzada"
        univ_name = "Universitat Autònoma de Barcelona"
        page_url = "https://www.uab.cat/web/postgrado/master-en-arritmologia-cardiaca-avanzada/plan-de-estudios-1206597472096.html/param1-4833_es/"

        html_arrit = "<html><head><title>Máster en Arritmología Cardíaca Avanzada - UAB</title></head><body><h1>Máster en Arritmología Cardíaca Avanzada</h1></body></html>"
        soup_arrit = BeautifulSoup(html_arrit, "html.parser")
        self.assertFalse(
            is_html_page_matching_degree(soup_arrit, target_title, univ_name, page_url),
            "Debe rechazar Arritmología Cardíaca para Matemática Avanzada"
        )

    def test_reject_medicina_transfusional_vs_portal_ambito_medicina(self):
        """Rechaza el portal general de ámbito de medicina cuando se busca Medicina Transfusional."""
        target_title = "Máster Universitario en Medicina Transfusional y Terapias Celulares Avanzadas"
        univ_name = "Universitat Autònoma de Barcelona"
        page_url = "https://www.uab.cat/web/estudis/masters-i-postgraus/masters-universitaris/per-ambits/medicina-1345667194024.html"

        html_portal = "<html><head><title>Màsters universitaris per àmbits: Medicina - UAB Barcelona</title></head><body><h1>Àmbit de Medicina</h1></body></html>"
        soup_portal = BeautifulSoup(html_portal, "html.parser")
        self.assertFalse(
            is_html_page_matching_degree(soup_portal, target_title, univ_name, page_url),
            "Debe rechazar el portal general de ámbito de medicina"
        )


if __name__ == "__main__":
    unittest.main()
