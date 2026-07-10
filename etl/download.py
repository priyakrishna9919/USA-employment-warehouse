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
PERF_PAGE = "https://www.dol.gov/agencies/eta/foreign-labor/performance"


def discover_lca_urls(min_fy: int = 2025) -> list[str]:
    """Scrape DOL's performance page for LCA disclosure .xlsx links.

    Immune to file-name pattern changes: whatever DOL links, we find.
    """
    import re

    html = requests.get(PERF_PAGE, timeout=60,
                        headers={"User-Agent": "Mozilla/5.0 (data-warehouse ETL)"}).text
    urls = re.findall(r'href="([^"]*LCA_Disclosure_Data[^"]*\.xlsx)"', html, re.I)
    out = []
    for u in urls:
        if not u.startswith("http"):
            u = "https://www.dol.gov" + u
        m = re.search(r"FY(\d{4})", u)
        if m and int(m.group(1)) >= min_fy and u not in out:
            out.append(u)
    return out


def load_config() -> dict:
    with open(ROOT / "config" / "sources.yaml") as f:
        return yaml.safe_load(f)


def download_file(url: str, dest: Path, chunk: int = 1 << 20, min_mb: float = 2.0) -> bool:
    """Stream a (potentially large) file to disk. Skips if already present.
    Tries dol.gov directly (3 attempts), then falls back to the Internet
    Archive's copy of the same public file (DOL's CDN sometimes blocks
    datacenter IPs like CI runners). Outcomes go to download_log.txt."""
    log = dest.parent / "download_log.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > min_mb * 1e6:
        print(f"  skip (exists): {dest.name}")
        return True
    tmp = dest.with_suffix(dest.suffix + ".part")
    release_url = ("https://github.com/priyakrishna9919/USA-employment-warehouse"
                   f"/releases/download/data-drop/{dest.name}")
    candidates = [release_url, url, f"https://web.archive.org/web/2026id_/{url}"]
    errors = []
    for cand in candidates:
        attempts = 3 if cand == url else 1 if "archive.org" in cand else 2
        for attempt in range(1, attempts + 1):
            try:
                with requests.get(cand, stream=True, timeout=(30, 600),
                                  headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) research-ETL"}) as r:
                    r.raise_for_status()
                    with open(tmp, "wb") as f:
                        for block in r.iter_content(chunk_size=chunk):
                            f.write(block)
                size_mb = tmp.stat().st_size / 1e6
                if size_mb < min_mb:
                    errors.append(f"{cand} -> too small ({size_mb:.2f} MB, likely error page)")
                    tmp.unlink(missing_ok=True)
                    break  # soft-404; try next candidate, not same URL again
                tmp.rename(dest)
                via = "direct" if cand == url else ("release asset" if "releases" in cand else "archive.org mirror (may be truncated!)")
                print(f"  ok ({via}): {dest.name} ({size_mb:.1f} MB)")
                with open(log, "a") as lf:
                    lf.write(f"OK   {dest.name} {size_mb:.1f}MB via {via}\n")
                return True
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{cand} attempt {attempt}: {type(exc).__name__}: {exc}")
                tmp.unlink(missing_ok=True)
    print(f"  FAILED {dest.name}: {' | '.join(errors[-2:])}", file=sys.stderr)
    with open(log, "a") as lf:
        lf.write(f"FAIL {dest.name}\n" + "".join(f"     {e}\n" for e in errors))
    return False


REPO = "priyakrishna9919/USA-employment-warehouse"


def download_release_assets() -> int:
    """Download every .xlsx asset attached to the 'data-drop' release.
    Routes files containing PERM to data/raw/perm, everything else to lca.
    Returns count downloaded. Names don't need to match config."""
    import os
    api = f"https://api.github.com/repos/{REPO}/releases/tags/data-drop"
    headers = {}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    try:
        resp = requests.get(api, timeout=30, headers=headers).json()
        assets = resp.get("assets", [])
        if not assets:
            print(f"release listing empty: {resp.get('message', 'no assets')}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"release lookup failed: {exc}", file=sys.stderr)
        return 0
    n = 0
    for a in assets:
        name = a["name"]
        if not name.lower().endswith(".xlsx"):
            continue
        sub = "perm" if "PERM" in name.upper() else "lca"
        if download_file(a["browser_download_url"], RAW / sub / name):
            n += 1
    print(f"[release] downloaded {n} asset(s) from data-drop")
    return n


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["lca", "perm"], default=None)
    parser.add_argument("--release", action="store_true",
                        help="download all xlsx assets from the data-drop GitHub release")
    parser.add_argument("--discover", action="store_true",
                        help="scrape dol.gov for current LCA file links instead of using config names")
    parser.add_argument("--min-fy", type=int, default=2025)
    args = parser.parse_args()

    failures = 0
    if args.release:
        n = download_release_assets()
        sys.exit(0 if n else 1)
    if args.discover:
        try:
            urls = discover_lca_urls(args.min_fy)
        except Exception as exc:  # noqa: BLE001
            print(f"discovery failed ({exc}); falling back to config", file=sys.stderr)
            urls = []
        print(f"[discover] found {len(urls)} LCA file(s) on dol.gov")
        for url in urls:
            if not download_file(url, RAW / "lca" / url.rsplit("/", 1)[-1]):
                failures += 1
        if urls:
            sys.exit(1 if failures == len(urls) else 0)

    cfg = load_config()
    sources = [args.only] if args.only else ["lca", "perm"]
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
