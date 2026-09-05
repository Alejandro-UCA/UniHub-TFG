"""Convierte evidencia HTTP del piloto en corpus reproducible, sin red."""
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import sqlite3
from collections import Counter
from dataclasses import asdict
from in_memory_web_snapshot import SnapshotEntry

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'Codigo' / 'Crawler' / 'Datos'
OUTPUT = DATA / 'web_snapshots' / 'v215_cache'


def main():
    pending = {}
    for path in (DATA / 'planes_estudio').glob('*/*.json'):
        record = json.loads(path.read_text(encoding='utf-8'))
        if not (record.get('calidad_datos') or {}).get('publicable'):
            pending[(str(record.get('universidad_codigo', '')).zfill(3), str(record.get('codigo_estudio', '')))] = str(path.relative_to(ROOT))
    connection = sqlite3.connect((DATA / 'crawl_ledger.sqlite3').as_uri() + '?mode=ro', uri=True)
    rows = connection.execute('SELECT url, university_code, degree_code, content_type, content_sha256, cache_path, cache_updated_at '
                              'FROM crawl_ledger WHERE http_status=200 AND robots_allowed=1 AND cache_path IS NOT NULL').fetchall()
    connection.close()
    counts = Counter()
    entries, associations, provenance = [], [], []
    for url, university, degree, content_type, expected_hash, raw_path, captured_at in rows:
        record_path = pending.get((str(university).zfill(3), str(degree)))
        if not record_path:
            continue
        counts['associated_responses'] += 1
        # Nunca seguir rutas del ledger a código/datos originales fuera del piloto.
        source = DATA / 'http_cache' / PureWindowsPath(raw_path).name
        if not source.is_file():
            counts['body_missing'] += 1
            continue
        body = source.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        if not expected_hash or expected_hash != digest:
            counts['hash_missing_or_mismatched'] += 1
            continue
        relative = 'bodies/' + digest + '.body'
        target = OUTPUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError('Conflicto de integridad en el corpus destino')
        else:
            shutil.copyfile(source, target)
        entries.append(asdict(SnapshotEntry(url, url, 200, content_type or '', digest, len(body), relative)))
        associations.append({'record_path': record_path, 'url': url})
        provenance.append({'url': url, 'cache_updated_at': captured_at, 'sha256': digest,
                           'robots_allowed': True, 'final_url_available': False})
        counts['frozen'] += 1
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, payload in [('manifest.json', {'schema': 1, 'entries': entries}),
                          ('associations.json', associations), ('provenance.json', provenance)]:
        target = OUTPUT / name
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, target)
    result = {'counts': dict(counts), 'pending_records_in_snapshot': len({item['record_path'] for item in associations}),
              'network_calls': 0, 'snapshot': str(OUTPUT)}
    (DATA / 'audits' / 'cache_freeze_v215.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
