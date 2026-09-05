"""Asocia documentos adquiridos a registros por sus referencias ya almacenadas."""
import argparse
import json
from pathlib import Path
from in_memory_web_snapshot import DiskWebSnapshot

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'Codigo' / 'Crawler' / 'Datos'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    directory = args.snapshot.resolve()
    if not directory.is_relative_to(DATA / 'web_snapshots'):
        raise ValueError('Snapshot fuera del piloto')
    snapshot = DiskWebSnapshot().load_directory(directory)
    aliases = {url.rstrip('/'): snapshot._files[url.rstrip('/')][0].url for url in snapshot.urls}
    associations = []
    for path in (DATA / 'planes_estudio').glob('*/*.json'):
        record = json.loads(path.read_text(encoding='utf-8'))
        if (record.get('calidad_datos') or {}).get('publicable'):
            continue
        urls = [record.get(key) for key in ('web_fuente_directa_url', 'web', 'boe_url')]
        urls.extend(record.get('all_boe_urls') or [])
        urls.extend(item.get('url') for item in record.get('fuentes', []) if isinstance(item, dict))
        matched = {aliases[url.split('#', 1)[0].rstrip('/')]
                   for url in urls if isinstance(url, str) and url.split('#', 1)[0].rstrip('/') in aliases}
        associations.extend({'record_path': str(path.relative_to(ROOT)), 'url': url} for url in sorted(matched))
    (directory / 'associations.json').write_text(json.dumps(associations, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'associations': len(associations), 'records': len({item['record_path'] for item in associations})}))


if __name__ == '__main__':
    main()
