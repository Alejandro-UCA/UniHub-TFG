"""Evalúa evidencia asociada por ledger, en procesos aislados y sin red."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from in_memory_web_snapshot import DiskWebSnapshot
from snapshot_promotion_campaign import _candidate_plan

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'Codigo' / 'Crawler' / 'Datos'
SNAPSHOT = DATA / 'web_snapshots' / 'v215_cache'
OUTPUT = DATA / 'audits' / 'cache_candidates_v215'
_WORKER_SNAPSHOT = None


def initialize_worker(directory):
    global _WORKER_SNAPSHOT
    _WORKER_SNAPSHOT = DiskWebSnapshot().load_directory(directory)


def evaluate(item):
    snapshot = _WORKER_SNAPSHOT or DiskWebSnapshot().load_directory(SNAPSHOT)
    record_path = (ROOT / item['record_path']).resolve()
    if not record_path.is_relative_to(DATA / 'planes_estudio'):
        raise ValueError('Registro fuera del piloto')
    record = json.loads(record_path.read_text(encoding='utf-8'))
    candidate = {'url': item['url'], 'title': record['titulo'],
                 'university': record['universidad_nombre'],
                 'academic_level': record.get('nivel_academico', ''),
                 'codigo_estudio': record['codigo_estudio']}
    try:
        with patch('socket.socket.connect', side_effect=AssertionError('Red prohibida durante el parser')):
            entry, body = snapshot.get(item['url'])
            plan, diagnostic = _candidate_plan(candidate, entry, body)
        result = {**item, 'candidate': candidate, 'diagnostic': diagnostic,
                  'source_sha256': entry.sha256,
                  'record_sha256': hashlib.sha256(record_path.read_bytes()).hexdigest(),
                  'network_calls': 0}
        if diagnostic.get('outcome') == 'recoverable_publicable':
            result['plan'] = plan
        return result
    except Exception as exc:
        return {**item, 'diagnostic': {'outcome': 'parser_error', 'error': str(exc)[:500]}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kind', choices=['html', 'pdf', 'all'], default='html')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    directory = args.snapshot.resolve()
    output = args.output.resolve()
    if not directory.is_relative_to(DATA) or not output.is_relative_to(DATA):
        raise ValueError('Corpus y resultados deben estar dentro del piloto')
    associations = json.loads((directory / 'associations.json').read_text(encoding='utf-8'))
    metadata = {raw['url']: raw for raw in json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))['entries']}
    selected = []
    for item in associations:
        kind = metadata[item['url']]['content_type'].lower()
        if args.kind != 'all' and args.kind not in kind:
            continue
        key = hashlib.sha256((item['record_path'] + '\n' + item['url']).encode()).hexdigest()
        path = output / (key + '.json')
        if not path.exists():
            selected.append((item, path))
    output.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    print(json.dumps({'queued': len(selected), 'kind': args.kind}), flush=True)
    with ProcessPoolExecutor(max_workers=max(1, min(args.workers, 4)),
                             initializer=initialize_worker, initargs=(directory,)) as executor:
        futures = {executor.submit(evaluate, item): path for item, path in selected}
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            path = futures[future]
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            counts[result['diagnostic']['outcome']] += 1
            if index % 25 == 0 or index == len(futures):
                print(json.dumps({'processed': index, 'total': len(futures), 'counts': dict(counts)}), flush=True)


if __name__ == '__main__':
    main()
