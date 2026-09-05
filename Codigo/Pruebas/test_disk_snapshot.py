import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from in_memory_web_snapshot import DiskWebSnapshot, InMemoryWebSnapshot, SnapshotEntry, SnapshotMiss
from snapshot_promotion_campaign import _candidate_plan


class DiskSnapshotTests(unittest.TestCase):
    def test_reads_lazily_checks_hash_and_never_falls_back_to_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = b'<h1>Plan</h1>'
            entry = SnapshotEntry('https://example.edu/plan', 'https://example.edu/plan',
                                  200, 'text/html', hashlib.sha256(body).hexdigest(), len(body), 'body.html')
            memory = InMemoryWebSnapshot()
            memory.add(entry, body)
            memory.save_directory(root)
            snapshot = DiskWebSnapshot().load_directory(root)
            self.assertEqual(body, snapshot.content(entry.url))
            with self.assertRaises(SnapshotMiss):
                snapshot.content('https://example.edu/missing')
            (root / 'body.html').write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                snapshot.content(entry.url)
            self.assertEqual(0, snapshot.network_calls)

    def test_manifest_cannot_escape_snapshot_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = dict(url='https://example.edu', final_url='', status_code=200,
                       content_type='text/html', sha256='', byte_length=0, relative_path='../outside')
            (root / 'manifest.json').write_text(json.dumps({'entries': [raw]}), encoding='utf-8')
            with self.assertRaises(ValueError):
                DiskWebSnapshot().load_directory(root)

    def test_doctorate_uses_research_lines_instead_of_ects(self):
        title = 'Programa de Doctorado en Biología Molecular'
        body = ('<h1>' + title + '</h1><h2>Líneas de Investigación</h2><ul>'
                '<li>Genómica de Poblaciones y Biología Molecular</li>'
                '<li>Neurobiología Celular y Desarrollo Embrionario</li></ul>').encode()
        url = 'https://example.edu/doctorado/biologia-molecular'
        entry = SnapshotEntry(url, url, 200, 'text/html', hashlib.sha256(body).hexdigest(), len(body), 'page.html')
        candidate = dict(url=url, title=title, university='Universidad de Prueba',
                         academic_level='Doctor - RD 99/2011 (0)', codigo_estudio='TEST1')
        plan, diagnostic = _candidate_plan(candidate, entry, body)
        self.assertEqual('recoverable_publicable', diagnostic['outcome'])
        self.assertEqual(2, len(plan['elementos_curriculares']))
        self.assertTrue(all(item['creditos_ects'] is None for item in plan['elementos_curriculares']))
