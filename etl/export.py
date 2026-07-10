"""Export the warehouse to a parquet file consumed by the static dashboard.

The dashboard (docs/index.html) runs DuckDB-WASM in the browser and queries
this file directly over HTTP - no server needed, works on GitHub Pages.

Usage: python -m etl.export
"""
from __future__ import annotations

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse.duckdb"
OUT = ROOT / "docs" / "data" / "sponsorships.parquet"


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit("Warehouse not found. Run `make sample` or `make load` first.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    con.execute(f"""
        COPY (
            SELECT case_status, visa_class, fiscal_year, job_title, annual_wage,
                   prevailing_wage, employer_name, is_university,
                   soc_code, soc_title, job_category, worksite_city, worksite_state
            FROM v_sponsorships
        ) TO '{OUT.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    n = con.execute("SELECT COUNT(*) FROM v_sponsorships").fetchone()[0]
    print(f"exported {n:,} rows -> {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")
    perm_n = con.execute("SELECT COUNT(*) FROM perm_filings").fetchone()[0]
    if perm_n:
        perm_out = OUT.parent / "perm.parquet"
        con.execute(f"COPY (SELECT * FROM v_perm) TO '{perm_out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        print(f"exported {perm_n:,} PERM rows -> {perm_out}")


if __name__ == "__main__":
    main()
