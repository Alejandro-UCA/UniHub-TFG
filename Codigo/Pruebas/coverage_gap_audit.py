"""Mide cobertura y disponibilidad de evidencia, sin red ni escritura de planes."""
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Codigo' / 'Crawler'))
from data_quality import assess_plan_quality
from in_memory_web_snapshot import InMemoryWebSnapshot, SnapshotMiss

DATA = ROOT / 'Codigo' / 'Crawler' / 'Datos'


def main():
    snapshot = InMemoryWebSnapshot().load_directory(DATA / 'web_snapshots' / 'v204')
    counts = Counter()
    pending = Counter()
    missing_urls = Counter()
    for path in sorted((DATA / 'planes_estudio').glob('*/*.json')):
        record = json.loads(path.read_text(encoding='utf-8'))
        counts['records'] += 1
        quality = assess_plan_quality(record, record.get('origen_fuente'))
        if quality['publicable']:
            counts['verified'] += 1
            continue
        counts['pending'] += 1
        pending[quality['completitud']] += 1
        urls = [record.get(key) for key in ('web_fuente_directa_url', 'web', 'boe_url')]
        urls.extend(record.get('all_boe_urls') or [])
        urls.extend(item.get('url') for item in record.get('fuentes', []) if isinstance(item, dict))
        urls = {url for url in urls if isinstance(url, str) and url.startswith(('http://', 'https://'))}
        if urls:
            counts['pending_with_stored_url'] += 1
        else:
            counts['pending_without_stored_url'] += 1
        usable = False
        for url in urls:
            try:
                entry, _ = snapshot.get(url.split('#', 1)[0])
                usable |= 200 <= entry.status_code < 300
            except SnapshotMiss:
                missing_urls[url] += 1
        counts['pending_with_snapshot_response' if usable else 'pending_without_snapshot_response'] += 1
    result = {
        'counts': dict(counts),
        'pending_by_completeness': dict(pending),
        'verified_percentage': 100 * counts['verified'] / counts['records'],
        'target_records': -(-95 * counts['records'] // 100),
        'missing_unique_urls': len(missing_urls),
        'network_calls': snapshot.network_calls,
        'interpretation': 'Una respuesta 2xx disponible no garantiza identidad, vigencia ni currículo completo. '
                          'Sin respuesta asociada no se puede corregir la extracción mediante reproducción directa. '
                          'No se excluyen registros del denominador ni se considera ausencia de fuente como éxito.',
    }
    output = DATA / 'audits' / 'coverage_gap_v213.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (DATA / 'audits' / 'acquisition_missing_v213.json').write_text(json.dumps({
        'mode': 'offline_acquisition_backlog',
        'policy': 'Sólo URLs ya almacenadas, ausentes del snapshot. Antes de adquirir, '
                  'aplicar Downloader institucional, robots y límites del proyecto. '
                  'Guardar otro snapshot; no sobrescribir v204.',
        'urls': [{'url': url, 'pending_records': count}
                 for url, count in missing_urls.most_common()],
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
