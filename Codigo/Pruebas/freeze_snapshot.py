"""Genera un manifiesto inmutable de los JSON de una campaña."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone


def freeze(root: str, output: str) -> dict:
    data_dir = os.path.join(root, "Codigo", "Crawler", "Datos")
    records = []
    for current, _, names in os.walk(data_dir):
        for name in sorted(names):
            path = os.path.join(current, name)
            if not os.path.isfile(path):
                continue
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            records.append({"path": os.path.relpath(path, root), "sha256": digest.hexdigest(), "bytes": os.path.getsize(path)})
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": os.path.abspath(root),
        "file_count": len(records),
        "files": records,
    }
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"root": manifest["root"], "file_count": manifest["file_count"], "output": os.path.abspath(output)}, ensure_ascii=False))
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    freeze(args.root, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
