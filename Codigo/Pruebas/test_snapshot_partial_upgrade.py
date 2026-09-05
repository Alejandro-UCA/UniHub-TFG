import unittest
import hashlib
import json
import tempfile
import io
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from snapshot_promotion_campaign import _protect_existing_plan
import snapshot_promotion_campaign as campaign
from in_memory_web_snapshot import InMemoryWebSnapshot, SnapshotEntry


class PartialUpgradeTests(unittest.TestCase):
    def test_real_campaign_archives_partial_and_preserves_other_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plans = root / 'planes'
            target = plans / 'uni' / 'TEST1.json'
            target.parent.mkdir(parents=True)
            url = 'https://example.edu/master/ciencia-datos/plan'
            title = 'Máster Universitario en Ciencia de Datos'
            original = {'codigo_estudio': 'TEST1', 'titulo': title,
                        'universidad_codigo': 'TST',
                        'universidad_nombre': 'Universidad de Prueba',
                        'nivel_academico': 'Máster', 'web_fuente_directa_url': url,
                        'origen_fuente': 'web_oficial_universidad',
                        'precios': {'curso': '2026-27', 'importe': 1200},
                        'plan_estudios': {'elementos_curriculares': [
                            {'nombre_elemento': 'Álgebra', 'creditos_ects': '6', 'caracter': 'OB'}]}}
            target.write_text(json.dumps(original), encoding='utf-8')
            original_bytes = target.read_bytes()
            names = ['Álgebra', 'Cálculo', 'Estadística', 'Probabilidad', 'Programación',
                     'Bases de datos', 'Optimización', 'Aprendizaje automático',
                     'Visualización', 'Trabajo Fin de Máster']
            body = ('<h1>' + title + '</h1><table><tr><th>Asignatura</th><th>ECTS</th></tr>'
                    + ''.join('<tr><td>' + name + '</td><td>6</td></tr>' for name in names)
                    + '</table>').encode()
            snapshot = InMemoryWebSnapshot()
            snapshot.add(SnapshotEntry(url, url, 200, 'text/html',
                         hashlib.sha256(body).hexdigest(), len(body), 'page.html'), body)
            snapshot.save_directory(root / 'snapshot')
            audit = root / 'dry_run.json'
            audit.write_text(json.dumps({'candidates': [{
                'outcome': 'recoverable_publicable', 'url': url, 'title': title,
                'university': 'Universidad de Prueba', 'academic_level': 'Máster'}]}), encoding='utf-8')
            with patch.multiple(campaign, ROOT=root, PLAN_DIR=plans,
                                SNAPSHOT_DIR=root / 'snapshot', DRY_RUN_AUDIT=audit,
                                OUTPUT=root / 'result.json', BACKUP_DIR=root / 'backup'):
                with redirect_stdout(io.StringIO()):
                    campaign.main()
            result = json.loads((root / 'result.json').read_text(encoding='utf-8'))
            updated = json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(1, result['counts']['promoted'])
            self.assertEqual(original_bytes, (root / 'backup' / 'uni' / 'TEST1.json').read_bytes())
            self.assertEqual(original['precios'], updated['precios'])
            self.assertTrue(updated['calidad_datos']['publicable'])
            self.assertTrue(updated['contrato_datos']['valid'])
            self.assertEqual(campaign._stable_degree_snapshot_hash(updated), updated['snapshot_hash'])
            self.assertEqual(1, result['changes'][0]['before_element_count'])
            self.assertEqual(0, result['network_calls'])

    def test_partial_detail_does_not_freeze_recovery(self):
        record = {'plan_estudios': {'elementos_curriculares': [{'nombre_elemento': 'Análisis'}]}}
        with patch('snapshot_promotion_campaign.assess_plan_quality', return_value={'publicable': False}):
            self.assertFalse(_protect_existing_plan(record))

    def test_stored_verified_plan_is_protected_even_if_quality_changed(self):
        with patch('snapshot_promotion_campaign.assess_plan_quality', return_value={'publicable': False}):
            self.assertTrue(_protect_existing_plan({'calidad_datos': {'publicable': True}}))

    def test_recomputed_verified_plan_is_protected(self):
        with patch('snapshot_promotion_campaign.assess_plan_quality', return_value={'publicable': True}):
            self.assertTrue(_protect_existing_plan({'calidad_datos': {'publicable': False}}))
