"""Busca resoluciones curriculares para pendientes y congela cada respuesta."""
import argparse
from collections import defaultdict
import hashlib
import itertools
import json
from pathlib import Path

import acquire_missing_evidence as acquisition
import boe_search_discovery
from boe_search_discovery import discover_boe_candidates, build_boe_search_queries
from in_memory_web_snapshot import DiskWebSnapshot

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'Codigo' / 'Crawler' / 'Datos'
OUTPUT = DATA / 'web_snapshots' / 'v217_boe_search'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=4)
    args = parser.parse_args()
    discovery_revision = hashlib.sha256(Path(boe_search_discovery.__file__).read_bytes()).hexdigest()
    acquisition.OUTPUT = OUTPUT
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results_dir = OUTPUT / 'discovery'
    results_dir.mkdir(exist_ok=True)
    manifest_path = OUTPUT / 'manifest.json'
    entries = {item['url']: item for item in json.loads(manifest_path.read_text(encoding='utf-8')).get('entries', [])} if manifest_path.exists() else {}
    associations_path = OUTPUT / 'associations.json'
    associations = json.loads(associations_path.read_text(encoding='utf-8')) if associations_path.exists() else []

    def save_manifest():
        temporary = manifest_path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'schema': 1, 'entries': list(entries.values())}, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(manifest_path)

    def fetch_text(url):
        if url not in entries:
            response = acquisition.acquire_one(url)
            if not response.get('entry'):
                raise RuntimeError(response)
            entries[url] = response['entry']
            save_manifest()
        entry, body = DiskWebSnapshot().load_directory(OUTPUT).get(url)
        if entry.status_code != 200:
            raise RuntimeError(f'HTTP {entry.status_code}')
        return body.decode('utf-8', errors='replace')

    groups = defaultdict(list)
    for path in sorted((DATA / 'planes_estudio').glob('*/*.json')):
        record = json.loads(path.read_text(encoding='utf-8'))
        if (record.get('calidad_datos') or {}).get('publicable'):
            continue
        if not any(word in str(record.get('nivel_academico', '')).casefold() for word in ('grado', 'master', 'máster')):
            continue
        queries = build_boe_search_queries(record['universidad_nombre'], record['titulo'], limit=2)
        key = hashlib.sha256((str(path.relative_to(ROOT)) + json.dumps(queries) + discovery_revision).encode()).hexdigest()
        if not (results_dir / (key + '.json')).exists():
            groups[record['universidad_nombre']].append((path, record, key))
    selected = itertools.islice((item for row in itertools.zip_longest(*groups.values()) for item in row if item), max(1, args.limit))
    for index, (path, record, key) in enumerate(selected, 1):
        result = discover_boe_candidates(record['universidad_nombre'], record['titulo'],
                                        record['nivel_academico'], fetch_text,
                                        query_limit=2, result_limit=3, document_limit=5, delay=1)
        acquired = 0
        for candidate in result.get('records', []):
            url = candidate['url']
            if url not in entries:
                response = acquisition.acquire_one(url)
                if not response.get('entry'):
                    continue
                entries[url] = response['entry']
                save_manifest()
            item = {'record_path': str(path.relative_to(ROOT)), 'url': url}
            if item not in associations:
                associations.append(item)
            acquired += 1
        result['record_path'] = str(path.relative_to(ROOT))
        result['acquired_curriculum_candidates'] = acquired
        (results_dir / (key + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        associations_path.write_text(json.dumps(associations, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'processed': index, 'title': record['titulo'], 'candidates': acquired,
                          'errors': result.get('errors', [])}, ensure_ascii=False), flush=True)
    save_manifest()


if __name__ == '__main__':
    main()
