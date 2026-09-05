"""Reevalúa sólo cambios de total declarado sobre la extracción completa v213.

Los parsers y filtros restantes son los de v213. Se conservan sus resultados
PDF y HTML cuyo total no cambia; se repite toda la extracción de las URLs afectadas.
"""
import hashlib
import json
from collections import Counter, defaultdict
from bs4 import BeautifulSoup
import snapshot_candidate_audit as audit
from curriculum_recovery import infer_declared_total_ects
from in_memory_web_snapshot import InMemoryWebSnapshot


def main():
    base_path = audit.DATA / 'audits' / 'snapshot_candidate_audit_v213.json'
    result = json.loads(base_path.read_text(encoding='utf-8'))
    snapshot = InMemoryWebSnapshot().load_directory(audit.SNAPSHOT_DIR)
    candidates, _ = audit._pending_candidates()
    grouped = defaultdict(list)
    for item in candidates:
        grouped[item['url']].append(item)
    previous = defaultdict(list)
    for item in result['candidates']:
        previous[item['url']].append(item)
    revised = []
    results = []
    for url, items in previous.items():
        first = items[0]
        if 'html' not in first.get('content_type', '') or not 200 <= first.get('status_code', 0) < 300:
            results.extend(items)
            continue
        _, body = snapshot.get(url)
        total = infer_declared_total_ects(BeautifulSoup(body, 'html.parser'))
        comparable = [item for item in items if 'declared_total_ects' in item]
        if comparable and any(item['declared_total_ects'] != total for item in comparable):
            results.extend(audit._results_for_url(snapshot, url, grouped[url]))
            revised.append(url)
        else:
            results.extend(items)
    result['candidates'] = results
    result['counts'] = dict(Counter(item['outcome'] for item in results))
    result['incremental_total_revalidation'] = {
        'base_audit': str(base_path),
        'base_sha256': hashlib.sha256(base_path.read_bytes()).hexdigest(),
        'reprocessed_urls': revised,
        'scope': 'Sólo cambia la gramática del total declarado desde v213.',
    }
    result['network_calls'] = snapshot.network_calls
    output = base_path.with_name('snapshot_candidate_audit_v214.json')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    audit.SUMMARY_OUTPUT = audit.SUMMARY_OUTPUT.with_name('AUDITORIA_CANDIDATOS_SNAPSHOT_v214.md')
    audit._write_summary(result)
    print(json.dumps({'counts': result['counts'], 'reprocessed_urls': revised,
                      'network_calls': snapshot.network_calls}))


if __name__ == '__main__':
    main()
