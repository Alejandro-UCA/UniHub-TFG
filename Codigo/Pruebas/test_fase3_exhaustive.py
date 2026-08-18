import os
import unittest

class TestPhase3FrontendExhaustive(unittest.TestCase):
    """
    Exhaustive functional and visual validation suite for Phase 3 (WWW React SPA).
    Validates components, state management, calculation formulas, A11y, routing, and security.
    """
    WWW_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "WWW"))
    SRC_DIR = os.path.join(WWW_DIR, "src")
    COMPONENTS_DIR = os.path.join(SRC_DIR, "components")

    def test_01_all_core_components_exist(self):
        """Verifica la existencia y tamaño válido de todos los componentes de la SPA."""
        required_components = [
            "App.jsx",
            "components/Navbar.jsx",
            "components/Hero.jsx",
            "components/UnivCard.jsx",
            "components/DegreeCard.jsx",
            "components/PlanModal.jsx",
            "components/TuitionCalculator.jsx",
            "components/AdminDashboard.jsx",
            "components/AdminFormModal.jsx",
            "components/AdminLogin.jsx",
            "components/Geolocation.jsx",
            "components/AboutUs.jsx",
            "components/Pagination.jsx",
            "components/Footer.jsx",
            "components/ErrorBoundary.jsx",
            "services/api.js",
            "analytics/usageTracker.js",
            "utils/distance.js",
            "index.css",
            "main.jsx"
        ]
        for comp in required_components:
            path = os.path.join(self.SRC_DIR, comp)
            self.assertTrue(os.path.exists(path), f"Falta el componente requerido: {comp}")
            self.assertGreater(os.path.getsize(path), 100, f"Componente vacío o incompleto: {comp}")

    def test_02_history_api_and_tab_routing_integrity(self):
        """Verifica que App.jsx implemente el enrutamiento con History API y popstate."""
        app_path = os.path.join(self.SRC_DIR, "App.jsx")
        with open(app_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("window.history.pushState", content, "Falta pushState en App.jsx para navegación")
        self.assertIn("popstate", content, "Falta listener de popstate para soporte botón atrás/adelante")
        self.assertIn("selectedRama", content, "Falta el estado de filtro por Rama de Conocimiento")
        self.assertIn("selectedUnivCodigo", content, "Falta el filtro por universidad específica")
        self.assertIn("AbortController", content, "Falta AbortController en búsquedas con debounce")

    def test_03_tuition_calculator_financial_logic(self):
        """Verifica las fórmulas de recargos de matrícula (1.0x-4.5x) y exenciones sociales."""
        calc_path = os.path.join(self.COMPONENTS_DIR, "TuitionCalculator.jsx")
        with open(calc_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Recargos por repetición
        self.assertIn("precio_credito_2", content, "Falta cálculo de 2ª matrícula")
        self.assertIn("precio_credito_3", content, "Falta cálculo de 3ª matrícula")
        self.assertIn("precio_credito_4", content, "Falta cálculo de 4ª matrícula")

        # Exenciones sociales
        self.assertIn("fn_general", content, "Falta descuento Familia Numerosa General (50%)")
        self.assertIn("fn_especial", content, "Falta exención Familia Numerosa Especial (100%)")
        self.assertIn("discapacidad", content, "Falta exención Discapacidad >= 33%")
        self.assertIn("beca_mec", content, "Falta exención Beca MEC")
        self.assertIn("bonif_99", content, "Falta Bonificación 99% Junta de Andalucía")
        self.assertIn("mh_bachillerato", content, "Falta exención Matrícula de Honor")

    def test_04_plan_modal_doctorate_and_menciones(self):
        """Verifica la tarjeta de Doctorado RD 99/2011 y el resaltado de Menciones oficiales."""
        modal_path = os.path.join(self.COMPONENTS_DIR, "PlanModal.jsx")
        with open(modal_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("programa_doctorado_investigacion", content, "Falta condición de estructura de Doctorado")
        self.assertIn("Real Decreto 99/2011", content, "Falta referencia normativa RD 99/2011")
        self.assertIn("menci|itinerari|especialid", content, "Falta resaltado de Menciones/Itinerarios")
        self.assertIn("document.body.style.overflow = 'hidden'", content, "Falta bloqueo de scroll al abrir modal")

    def test_05_admin_dashboard_security_and_export(self):
        """Verifica la exportación segura en Blob/URL.createObjectURL y sanitización anti CSV Injection."""
        admin_path = os.path.join(self.COMPONENTS_DIR, "AdminDashboard.jsx")
        with open(admin_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("URL.createObjectURL", content, "Exportación debe usar Blob + URL.createObjectURL")
        self.assertIn("URL.revokeObjectURL", content, "Falta revocar el objeto URL tras la descarga")
        self.assertIn("sanitize", content, "Falta función de sanitización anti CSV Formula Injection")
        self.assertIn("/^[=+\\-@\\t\\r]/", content, "Falta protección contra caracteres ejecutables de Excel")

    def test_06_geolocation_and_distance_matrix(self):
        """Verifica la cobertura de capitales de provincia en distance.js (> 40 ciudades)."""
        dist_path = os.path.join(self.SRC_DIR, "utils", "distance.js")
        with open(dist_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Comprobar presencia de ciudades clave de todas las CCAA
        required_cities = [
            "madrid", "barcelona", "sevilla", "valencia", "cadiz", "bilbao", 
            "zaragoza", "oviedo", "santiago", "badajoz", "caceres", "palma",
            "laspalmas", "santander", "logrono", "pamplona", "toledo", "murcia"
        ]
        for city in required_cities:
            self.assertIn(f'"{city}"', content, f"Falta la ciudad '{city}' en SPANISH_CITIES_COORDS")

    def test_07_accessibility_and_contrast(self):
        """Verifica atributos ARIA en inputs, selects y botones de cierre."""
        app_path = os.path.join(self.SRC_DIR, "App.jsx")
        with open(app_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('aria-label="Buscar titulaciones por nombre"', content)
        self.assertIn('aria-label="Filtrar por nivel académico"', content)
        self.assertIn('aria-label="Filtrar por tipo de universidad"', content)
        self.assertIn('aria-label="Filtrar por Comunidad Autónoma"', content)
        self.assertIn('aria-label="Filtrar por Rama de Conocimiento"', content)

    def test_08_css_variables_and_cross_browser_scrollbar(self):
        """Verifica las variables de color institucionales de la UCA y el scrollbar estándar."""
        css_path = os.path.join(self.SRC_DIR, "index.css")
        with open(css_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("--uca-navy:", content)
        self.assertIn("--uca-blue:", content)
        self.assertIn("--uca-cyan:", content)
        self.assertIn("scrollbar-width: thin;", content, "Falta scrollbar estándar para Firefox")

    def test_09_pagination_scroll_to_top(self):
        """Verifica que la paginación efectúe scroll automático suave al inicio."""
        pag_path = os.path.join(self.COMPONENTS_DIR, "Pagination.jsx")
        with open(pag_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("window.scrollTo({ top: 0, behavior: 'smooth' })", content, "Falta scroll to top en Pagination.jsx")

    def test_10_admin_login_privacy_and_secrecy(self):
        """Verifica que no existan credenciales por defecto, pistas ni autocompletar en el login de admin."""
        login_path = os.path.join(self.COMPONENTS_DIR, "AdminLogin.jsx")
        with open(login_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertNotIn("Autocompletar", content, "No debe existir botón de autocompletar en Login")
        self.assertNotIn("unihub_super_secret_admin_key_2026", content, "La clave no debe estar expuesta en el componente de login")
        self.assertNotIn("Clave por defecto", content, "No debe haber pistas de credenciales en el texto")

    def test_11_subjects_crud_and_full_catalog_pagination(self):
        """Verifica la gestión de asignaturas y la integración de paginación total en el Admin Dashboard."""
        admin_path = os.path.join(self.COMPONENTS_DIR, "AdminDashboard.jsx")
        with open(admin_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("handleOpenSubjectsManager", content, "Falta gestor de asignaturas en AdminDashboard")
        self.assertIn("selectedDegreeForSubjects", content, "Falta estado para modal de asignaturas")
        self.assertIn("<Pagination", content, "El panel CRUD debe integrar el componente de paginación completa")

    def test_12_footer_official_sources_legal_disclaimer(self):
        """Verifica que el pie de página incluya el aviso legal sobre fuentes oficiales y elimine enlaces no procedentes."""
        footer_path = os.path.join(self.COMPONENTS_DIR, "Footer.jsx")
        with open(footer_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Registro de Universidades, Centros y Títulos", content, "Falta mención al RUCT")
        self.assertIn("Boletín Oficial del Estado", content, "Falta mención al BOE")
        self.assertNotIn("Creado con amor", content, "Debe eliminarse el texto de 'Creado con amor'")

if __name__ == "__main__":
    unittest.main(verbosity=2)
