"""Promueve resultados congelados por asociación explícita, con guardas e historial."""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from in_memory_web_snapshot import DiskWebSnapshot
import snapshot_promotion_campaign as campaign

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'Codigo' / 'Crawler' / 'Datos'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidates', type=Path, default=DATA / 'audits' / 'cache_candidates_v215')
    parser.add_argument('--snapshot', type=Path, default=DATA / 'web_snapshots' / 'v215_cache')
    parser.add_argument('--label', default='v215')
    args = parser.parse_args()
    if not args.label.isalnum():
        raise ValueError('Etiqueta no válida')
    for path in (args.candidates, args.snapshot):
        if not path.resolve().is_relative_to(DATA):
            raise ValueError('Ruta fuera del piloto')
    best = {}
    stale = 0
    for path in sorted(args.candidates.glob('*.json')):
        result = json.loads(path.read_text(encoding='utf-8'))
        if result['diagnostic'].get('outcome') != 'recoverable_publicable':
            continue
        target = (ROOT / result['record_path']).resolve()
        if not target.is_relative_to(DATA / 'planes_estudio'):
            raise ValueError('Registro fuera del piloto')
        if hashlib.sha256(target.read_bytes()).hexdigest() != result['record_sha256']:
            stale += 1
            continue
        prior = best.get(target)
        if prior is None or result['diagnostic']['element_count'] > prior['diagnostic']['element_count']:
            best[target] = result
    index, approved = {}, []
    for path, result in best.items():
        item = result['candidate']
        key = (item['university'], item['title'], campaign._url(item['url']))
        index.setdefault(key, []).append((path, json.loads(path.read_text(encoding='utf-8'))))
        approved.append({**item, 'outcome': 'recoverable_publicable'})
    dry_run = DATA / 'audits' / f'cache_promotion_{args.label}_input.json'
    dry_run.write_text(json.dumps({'candidates': approved, 'stale_candidates_rejected': stale},
                                  ensure_ascii=False, indent=2), encoding='utf-8')
    with patch.multiple(campaign, SNAPSHOT_DIR=args.snapshot, DRY_RUN_AUDIT=dry_run,
                        OUTPUT=DATA / 'audits' / f'cache_promotion_{args.label}.json',
                        BACKUP_DIR=DATA / 'history' / f'cache_promotion_{args.label}',
                        InMemoryWebSnapshot=DiskWebSnapshot), \
         patch.object(campaign, '_index_records', return_value=index):
        campaign.main()


if __name__ == '__main__':
    main()
