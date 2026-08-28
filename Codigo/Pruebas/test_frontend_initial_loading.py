import os
import unittest


APP_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "WWW", "src", "App.jsx"))


class TestFrontendInitialLoading(unittest.TestCase):
    def test_university_load_is_not_coupled_to_degree_page_size(self):
        with open(APP_PATH, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("const [degreeReloadToken, setDegreeReloadToken]", source)
        self.assertIn("}, []);\n\n  // Registrar la visita", source)
        self.assertIn("[initialDataLoaded, degreeCurrentPage, fetchDegreesPage, degreeReloadToken]", source)
        self.assertNotIn("}, [degreeItemsPerPage]);\n\n  // Registrar vista inicial", source)


if __name__ == "__main__":
    unittest.main()
