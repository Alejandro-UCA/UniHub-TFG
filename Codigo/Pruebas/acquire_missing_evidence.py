"""Adquisición acotada, reanudable y separada del procesamiento del piloto."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

from downloader import RUCTDownloader
from in_memory_web_snapshot import DiskWebSnapshot, SnapshotEntry

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'Codigo' / 'Crawler' / 'Datos'
OUTPUT = DATA / 'web_snapshots' / 'v216_live'


def acquire_one(url):
    started = time.monotonic()
    downloader = RUCTDownloader(delay=1.0, max_retries=1, timeout=15,
                                respect_robots=True, enable_http2=False)
    downloader.reset_university_context('', base_url=url)
    downloader.set_degree_context(hashlib.sha256(url.encode()).hexdigest()[:12])
    try:
        with downloader._request_with_retry(url, stream=True) as response:
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 25_000_000 or time.monotonic() - started > 65:
                    raise TimeoutError('Presupuesto de adquisición agotado')
                chunks.append(chunk)
            body = b''.join(chunks)
            digest = hashlib.sha256(body).hexdigest()
            relative = 'bodies/' + digest + '.body'
            target = OUTPUT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            # Sólo se escribe contenido nuevo en el corpus nuevo.
            if not target.exists():
                target.write_bytes(body)
            entry = SnapshotEntry(url, response.url or url, response.status_code,
                                  response.headers.get('Content-Type', ''), digest, len(body), relative)
            return {'url': url, 'entry': asdict(entry), 'status': 'acquired',
                    'robots_enforced': True, 'elapsed_seconds': time.monotonic() - started}
    except Exception as exc:
        return {'url': url, 'status': 'failed', 'error_type': type(exc).__name__,
                'error': str(exc)[:600], 'elapsed_seconds': time.monotonic() - started}
    finally:
        downloader.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=4)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    available = set()
    for directory in (DATA / 'web_snapshots' / 'v204', DATA / 'web_snapshots' / 'v215_cache'):
        if (directory / 'manifest.json').exists():
            available.update(url.rstrip('/') for url in DiskWebSnapshot().load_directory(directory).urls)
    receipts = OUTPUT / 'receipts'
    receipts.mkdir(parents=True, exist_ok=True)
    missing = json.loads((DATA / 'audits' / 'acquisition_missing_v213.json').read_text(encoding='utf-8'))['urls']
    # Favorecer documentos curriculares sobre portadas, con el mismo criterio
    # para todas las instituciones. No se fabrican rutas.
    missing.sort(key=lambda item: (not urlsplit(item['url']).path.lower().endswith('.pdf'),
                                   -item['pending_records'], item['url']))
    selected = []
    for item in missing:
        url = item['url']
        key = hashlib.sha256(url.encode()).hexdigest()
        if url.rstrip('/') in available or (receipts / (key + '.json')).exists():
            continue
        selected.append(url)
        if len(selected) >= max(1, args.limit):
            break
    print(json.dumps({'selected': len(selected)}), flush=True)
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as pool:
        for future in as_completed([pool.submit(acquire_one, url) for url in selected]):
            result = future.result()
            key = hashlib.sha256(result['url'].encode()).hexdigest()
            (receipts / (key + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(result, ensure_ascii=False), flush=True)
    entries = [item['entry'] for path in receipts.glob('*.json')
               if (item := json.loads(path.read_text(encoding='utf-8'))).get('entry')]
    temporary = OUTPUT / 'manifest.tmp'
    temporary.write_text(json.dumps({'schema': 1, 'entries': entries}, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(OUTPUT / 'manifest.json')


if __name__ == '__main__':
    main()
