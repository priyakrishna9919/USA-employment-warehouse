"""Download DOL OFLC disclosure files (LCA, PERM) into data/raw/.

Usage:  python -m etl.download            # download everything in config
        python -m etl.download --only lca
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"


def load_config() -> dict:
    with open(ROOT / "config" / "sources.yaml") as f:
        return yaml.safe_load(f)


def download_file(url: str, dest: Path, chunk: int = 1 << 20) -> bool:
    """Stream a (potentially large) file to disk. Skips if already present."""
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  skip (exists): {dest.name}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for block in r.iter_content(chunk_size=chunk):
                    f.write(block)
        tmp.rename(dest)
        print(f"  ok: {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  FAILED {url}: {exc}", file=sys.stderr)
        tmp.unlink(missing_ok=True)
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["lca", "perm"], default=None)
    args = parser.parse_args()

    cfg = load_config()
    sources = [args.only] if args.only else ["lca", "perm"]
    failures = 0
    for source in sources:
        section = cfg.get(source) or {}
        base = section.get("base_url", "")
        print(f"[{source}] downloading {len(section.get('files', []))} file(s)")
        for name in section.get("files", []):
            if not download_file(f"{base}/{name}", RAW / source / name):
                failures += 1
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
