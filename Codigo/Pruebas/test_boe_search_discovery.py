import json
import unittest

from boe_search_discovery import (
    build_boe_search_queries,
    discover_boe_candidates,
    discover_boe_candidates_from_summary,
    parse_boe_summary_json,
    parse_boe_search_results,
    rebuild_persisted_boe_candidates,
    needs_boe_curriculum_search,
)


SEARCH_HTML = """
<html><body>
<div class="listadoResult"><ul>
 <li class="resultado-busqueda">
  <p class="linea-dem">Universidades</p>
  <p class="linea-pub">BOE 45 de 22/02/2017 - III. Otras disposiciones</p>
  <p>Resolución de 6 de febrero de 2017, de la Universitat de València, por la que se publica el plan de estudios de Máster en Investigación y Desarrollo en Biotecnología y Biomedicina.</p>
  <a href="../buscar/doc.php?id=BOE-A-2017-1825" title="Ref. BOE-A-2017-1825">Más...</a>
 </li>
</ul></div>
</body></html>
"""


DOCUMENT_HTML = """
<html><head><title>Resolución de la Universitat de València por la que se publica el plan de estudios de Máster en Investigación y Desarrollo en Biotecnología y Biomedicina.</title></head>
<body><a href="/boe/dias/2017/02/22/pdfs/BOE-A-2017-1825.pdf">PDF</a></body></html>
"""


SUMMARY_JSON = """
{
  "status": {"code": "200", "text": "ok"},
  "data": {"item": {
      "identificador": "BOE-A-2017-1825",
      "titulo": "Resolución de la Universitat de València por la que se publica el plan de estudios de Máster en Investigación y Desarrollo en Biotecnología y Biomedicina",
      "url_pdf": {"texto": "https://www.boe.es/boe/dias/2017/02/22/pdfs/BOE-A-2017-1825.pdf"}
  }}
}
"""


class BoeSearchDiscoveryTests(unittest.TestCase):
    def test_search_does_not_replace_degree_with_master_or_legacy_diploma(self):
        from boe_search_discovery import _candidate_score
        for source in ('Máster en Turismo', 'Diplomado en Turismo'):
            self.assertIsNone(_candidate_score(
                {'title': 'Universidad de Prueba publica el plan de estudios de ' + source},
                '', 'Universidad de Prueba', 'Graduado o Graduada en Turismo'))

    def test_ruct_gender_variants_do_not_become_conjunctive_search_terms(self):
        queries = build_boe_search_queries('Universidad de Prueba',
                                          'Graduado o Graduada en Turismo por la Universidad de Prueba', limit=2)
        self.assertTrue(queries)
        self.assertTrue(all('graduado' not in query and 'graduada' not in query for query in queries))
        self.assertIn('turismo', queries[0])

    def test_bilingual_degree_does_not_require_both_languages_in_query(self):
        queries = build_boe_search_queries('Universidad de Prueba',
                                          'Graduado o Graduada en Bioinformática / Bachelor in Bioinformatics', limit=2)
        self.assertTrue(all('bachelor' not in query and 'bioinformatics' not in query for query in queries))

    def test_common_subject_word_does_not_validate_another_degree(self):
        from boe_search_discovery import _candidate_score
        self.assertIsNone(_candidate_score(
            {'title': 'Resolución de la Universitat de València por la que se publica el plan de estudios de Máster en Investigación en Psicología'},
            '', 'Universitat de València',
            'Máster Universitario en Investigación y Desarrollo en Biotecnología y Biomedicina'))

    def test_administrative_references_do_not_freeze_pending_record(self):
        record = {'codigo_estudio': 'TEST1', 'titulo': 'Grado en Química',
                  'nivel_academico': 'Grado', 'plan_estudios': None,
                  'all_boe_urls': ['https://example.edu/registro.pdf']}
        self.assertTrue(needs_boe_curriculum_search([{'url': record['all_boe_urls'][0]}], record))

    def test_first_visit_uses_ruct_candidates_before_searching(self):
        self.assertFalse(needs_boe_curriculum_search([{'url': 'https://example.edu/plan.pdf'}], {}))
        self.assertTrue(needs_boe_curriculum_search([], {}))

    def test_verified_plan_does_not_trigger_another_search(self):
        from unittest.mock import patch
        with patch('data_quality.assess_plan_quality', return_value={'publicable': True}):
            self.assertFalse(needs_boe_curriculum_search([{'url': 'https://example.edu/plan.pdf'}], {'plan_estudios': {}}))

    def test_queries_are_bounded_and_strip_administrative_suffix(self):
        queries = build_boe_search_queries(
            "Universitat de València",
            "Máster Universitario en Investigación y Desarrollo en Biotecnología y Biomedicina por la Universitat de València",
            "Máster",
            limit=2,
        )
        self.assertLessEqual(len(queries), 2)
        self.assertGreaterEqual(len(queries), 1)
        self.assertIn("investigacion", queries[0].lower())
        self.assertIn("valencia", queries[0].lower())

    def test_parse_results_extracts_official_document_metadata(self):
        records = parse_boe_search_results(SEARCH_HTML)
        self.assertEqual(1, len(records))
        self.assertEqual("BOE-A-2017-1825", records[0]["reference"])
        self.assertEqual("2017-02-22", records[0]["boe_date"])
        self.assertIn("plan de estudios", records[0]["title"].lower())

    def test_discovery_requires_title_and_institution_evidence(self):
        calls = []

        def fetcher(url):
            calls.append(url)
            if "redirector.php" in url:
                return SEARCH_HTML
            return DOCUMENT_HTML

        result = discover_boe_candidates(
            "Universitat de València",
            "Máster Universitario en Investigación y Desarrollo en Biotecnología y Biomedicina",
            "Máster",
            fetcher,
            query_limit=1,
            result_limit=4,
            document_limit=4,
            delay=0,
        )
        self.assertEqual(2, len(calls))
        self.assertEqual(1, len(result["records"]))
        self.assertTrue(result["records"][0]["url"].endswith("BOE-A-2017-1825.pdf"))
        self.assertEqual("boe_official_search", result["records"][0]["discovery"])

    def test_discovery_rejects_same_title_from_unrelated_institution(self):
        calls = []
        wrong_search = SEARCH_HTML.replace("Universitat de València", "Universidad de Otra Ciudad")
        wrong_document = DOCUMENT_HTML.replace("Universitat de València", "Universidad de Otra Ciudad")

        def fetcher(url):
            calls.append(url)
            return wrong_search if "redirector.php" in url else wrong_document

        result = discover_boe_candidates(
            "Universitat de València",
            "Máster Universitario en Investigación y Desarrollo en Biotecnología y Biomedicina",
            "Máster",
            fetcher,
            query_limit=1,
            result_limit=4,
            document_limit=4,
            delay=0,
        )
        self.assertEqual([], result["records"])

    def test_persisted_urls_are_rebuilt_with_bounded_generic_candidates(self):
        records = rebuild_persisted_boe_candidates(
            [
                "https://www.boe.es/boe/dias/2021/11/01/pdfs/BOE-A-2021-17696.pdf",
                "https://www.boe.es/boe/dias/2021/11/01/pdfs/BOE-A-2021-17696.pdf",
                "https://www.example.edu/plan.pdf",
                "javascript:void(0)",
            ],
            limit=2,
        )
        self.assertEqual(2, len(records))
        self.assertEqual("2021-11-01", records[0]["boe_date"])
        self.assertEqual("persisted_ruct_evidence", records[0]["discovery"])
        self.assertEqual("persisted_boe_candidate", records[0]["doc_type"])

    def test_persisted_candidates_do_not_claim_curricular_validity(self):
        records = rebuild_persisted_boe_candidates(["https://www.boe.es/boe/dias/2022/01/01/pdfs/test.pdf"])
        self.assertEqual(1, len(records))
        self.assertNotIn("publicable", records[0])
        self.assertNotIn("elementos_curriculares", records[0])

    def test_parse_summary_json_extracts_official_pdf_items(self):
        records = parse_boe_summary_json(SUMMARY_JSON)
        self.assertEqual(1, len(records))
        self.assertEqual("BOE-A-2017-1825", records[0]["reference"])
        self.assertTrue(records[0]["document_url"].endswith("BOE-A-2017-1825.pdf"))

    def test_summary_discovery_uses_date_and_requires_both_identities(self):
        calls = []

        def fetcher(url, **kwargs):
            calls.append((url, kwargs))
            return SUMMARY_JSON

        result = discover_boe_candidates_from_summary(
            "Universitat de València",
            "Máster Universitario en Investigación y Desarrollo en Biotecnología y Biomedicina",
            "Máster",
            "2017-02-22",
            fetcher,
            date_limit=1,
            item_limit=4,
            delay=0,
        )
        self.assertEqual(1, len(calls))
        self.assertIn("20170222", calls[0][0])
        self.assertEqual({"Accept": "application/json"}, calls[0][1]["request_headers"])
        self.assertEqual(1, len(result["records"]))
        self.assertEqual("boe_official_summary_api", result["records"][0]["discovery"])

        wrong = SUMMARY_JSON.replace("Universitat de València", "Universidad de Otra Ciudad")
        result_wrong = discover_boe_candidates_from_summary(
            "Universitat de València",
            "Máster Universitario en Investigación y Desarrollo en Biotecnología y Biomedicina",
            "Máster",
            "2017-02-22",
            lambda _url, **_kwargs: wrong,
            date_limit=1,
            delay=0,
        )
        self.assertEqual([], result_wrong["records"])

    def test_summary_limit_is_applied_after_candidate_filtering(self):
        payload = json.loads(SUMMARY_JSON)
        target = payload["data"]["item"]
        payload["data"] = {"items": [
            {
                "identificador": "BOE-A-2017-1",
                "titulo": "Resolución administrativa sin plan de estudios",
                "url_pdf": {"texto": "https://www.boe.es/boe/dias/2017/02/22/pdfs/BOE-A-2017-1.pdf"},
            },
            target,
        ]}
        result = discover_boe_candidates_from_summary(
            "Universitat de València",
            "Máster Universitario en Investigación y Desarrollo en Biotecnología y Biomedicina",
            "Máster",
            "2017-02-22",
            lambda _url, **_kwargs: json.dumps(payload, ensure_ascii=False),
            date_limit=1,
            item_limit=1,
            delay=0,
        )
        self.assertEqual(1, len(result["records"]))
        self.assertEqual("BOE-A-2017-1825", result["records"][0]["boe_reference"])


if __name__ == "__main__":
    unittest.main()
