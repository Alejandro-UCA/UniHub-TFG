import html
import unittest
from urllib.parse import quote
from unittest.mock import patch

import web_search_discovery as search_discovery

from web_search_discovery import (
    build_search_queries,
    discover_institutional_origins,
    discover_search_candidates,
    is_search_result_host_compatible,
    parse_search_results,
    rank_search_results,
    rank_institutional_origins,
    is_search_provider_challenge,
)


class WebSearchDiscoveryTests(unittest.TestCase):
    def test_parse_unwraps_provider_redirect_and_ignores_provider_links(self):
        target = "https://web.example.edu/studies/master/data-science"
        body = f'''
        <html><body>
          <a class="result__a" href="//duckduckgo.com/l/?uddg={quote(target)}&rut=abc">Plan</a>
          <a class="result__a" href="https://duckduckgo.com/about">About</a>
        </body></html>
        '''
        records = parse_search_results(body)
        self.assertEqual([target], [record["url"] for record in records])

    def test_parse_bing_html_result(self):
        target = "https://www.example.es/plan-estudios"
        body = f'<li class="b_algo"><h2><a href="{target}">Plan académico</a></h2><p>Detalle oficial</p></li>'
        records = parse_search_results(body, endpoint="https://www.bing.com/search")
        self.assertEqual([target], [record["url"] for record in records])

    def test_parse_duckduckgo_lite_result(self):
        target = "https://www.example.es/plan-estudios"
        body = f'<a class="result-link" href="{target}">Plan académico</a>'
        records = parse_search_results(body, endpoint="https://lite.duckduckgo.com/lite/")
        self.assertEqual([target], [record["url"] for record in records])

    def test_provider_challenge_is_distinguished_from_empty_results(self):
        self.assertTrue(is_search_provider_challenge("Unfortunately, bots use DuckDuckGo too. Please complete the following challenge"))
        self.assertFalse(is_search_provider_challenge("<html><body>No results</body></html>"))

    def test_parse_bing_encoded_redirect(self):
        import base64
        target = "https://www.example.es/plan-estudios"
        encoded = "a1" + base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
        body = f'<li class="b_algo"><h2><a href="https://www.bing.com/ck/a?u={encoded}">Plan académico</a></h2></li>'
        records = parse_search_results(body, endpoint="https://www.bing.com/search")
        self.assertEqual([target], [record["url"] for record in records])

    def test_parse_bing_rss_result(self):
        target = "https://www.example.es/plan-estudios"
        body = f'<rss><channel><item><title>Plan académico</title><link>{target}</link><description>Detalle oficial</description></item></channel></rss>'
        records = parse_search_results(body, endpoint="https://www.bing.com/search")
        self.assertEqual([target], [record["url"] for record in records])

    def test_host_policy_allows_same_organisation_alias_but_not_unrelated_host(self):
        self.assertTrue(
            is_search_result_host_compatible(
                "https://web.example.edu/plan", "https://www.example.es"
            )
        )
        self.assertTrue(
            is_search_result_host_compatible(
                "https://faculty.example.es/plan", "https://www.example.es"
            )
        )
        self.assertFalse(
            is_search_result_host_compatible(
                "https://example-other.edu/plan", "https://www.example.es"
            )
        )

    def test_rank_institutional_origin_excludes_encyclopedia_and_keeps_alias(self):
        records = [
            {"url": "https://es.wikipedia.org/wiki/Example_University", "title": "Example University", "snippet": "universidad"},
            {"url": "https://web.example.edu/", "title": "Example University", "snippet": "Portal institucional de la universidad"},
        ]
        ranked = rank_institutional_origins(records, "Example University", "https://www.example.es")
        self.assertEqual(["https://web.example.edu/"], [record["url"] for record in ranked])

    def test_institutional_origin_discovery_uses_one_bounded_query(self):
        body = '<li class="b_algo"><h2><a href="https://web.example.edu/">Example University</a></h2><p>Portal institucional de la universidad</p></li>'
        calls = []

        def fetcher(url):
            calls.append(url)
            return body

        result = discover_institutional_origins(
            "Example University", "https://www.example.es", fetcher, query_limit=1, delay=0
        )
        self.assertEqual(1, len(calls))
        self.assertEqual(["https://web.example.edu/"], [record["url"] for record in result["records"]])

    def test_rank_requires_degree_and_academic_evidence(self):
        records = [
            {
                "url": "https://www.example.es/news/data-science",
                "title": "Data science plan de estudios",
                "snippet": "official university page",
            },
            {
                "url": "https://www.example.es/contact",
                "title": "Contact",
                "snippet": "Data science university",
            },
            {
                "url": "https://unrelated.es/data-science-plan",
                "title": "Data science plan de estudios",
                "snippet": "university",
            },
        ]
        ranked = rank_search_results(
            records,
            "Example University",
            "Master in Data Science",
            "https://www.example.es",
        )
        self.assertEqual(1, len(ranked))
        self.assertEqual("https://www.example.es/news/data-science", ranked[0]["url"])

    def test_build_queries_is_generic_and_bounded(self):
        queries = build_search_queries(
            "Example University",
            "Master in Data Science",
            "Máster - RD 822/2021 (3)",
            limit=1,
        )
        self.assertEqual(1, len(queries))
        self.assertIn("plan de estudios", queries[0])
        self.assertNotIn("por la Universidad de", queries[0])

    def test_discovery_deduplicates_and_returns_traceable_records(self):
        target = "https://www.example.es/studies/master/data-science"
        body = (
            '<a class="result__a" href="'
            + html.escape(target)
            + '">Master Data Science plan de estudios</a>'
        )
        calls = []

        def fetcher(url):
            calls.append(url)
            return body

        result = discover_search_candidates(
            "Example University",
            "Master in Data Science",
            "master",
            "https://www.example.es",
            fetcher,
            query_limit=2,
            result_limit=4,
            delay=0,
        )
        self.assertEqual(2, len(calls))
        self.assertEqual([target], [record["url"] for record in result["records"]])
        self.assertEqual([], result["errors"])

    def test_discovery_falls_back_when_primary_provider_challenges(self):
        target = "https://www.example.es/studies/biology/plan"
        body = '<li class="b_algo"><h2><a href="' + html.escape(target) + '">Biology plan de estudios</a></h2></li>'
        calls = []

        def fetcher(url):
            calls.append(url)
            if "primary.example" in url:
                return "Unfortunately, bots use this provider. Please complete the following challenge"
            return body

        with patch.object(search_discovery, "WEB_SEARCH_DISCOVERY_ENDPOINT", "https://primary.example/search"), \
             patch.object(search_discovery, "WEB_SEARCH_DISCOVERY_FALLBACK_ENDPOINTS", ("https://fallback.example/search",)):
            result = discover_search_candidates(
                "Example University",
                "Biology",
                "grado",
                "https://www.example.es",
                fetcher,
                query_limit=1,
                result_limit=4,
                delay=0,
            )

        self.assertEqual(2, len(calls))
        self.assertEqual([target], [record["url"] for record in result["records"]])
        self.assertIn("provider_challenge", result["errors"])

    def test_fallback_endpoint_keeps_existing_query_parameters(self):
        calls = []

        def fetcher(url):
            calls.append(url)
            return "<html><body>No results</body></html>"

        with patch.object(search_discovery, "WEB_SEARCH_DISCOVERY_ENDPOINT", "https://primary.example/search"), \
             patch.object(search_discovery, "WEB_SEARCH_DISCOVERY_FALLBACK_ENDPOINTS", ("https://fallback.example/search?format=rss",)):
            discover_search_candidates(
                "Example University",
                "Biology",
                "grado",
                "https://www.example.es",
                fetcher,
                query_limit=1,
                result_limit=1,
                delay=0,
            )

        self.assertEqual(2, len(calls))
        self.assertIn("fallback.example/search?format=rss&q=", calls[1])


if __name__ == "__main__":
    unittest.main()
