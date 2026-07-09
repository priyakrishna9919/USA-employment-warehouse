"""Transform raw DOL LCA disclosure files and load them into DuckDB.

Handles both real DOL Excel files and the CSV sample. Idempotent: re-running
the same file will not create duplicates (upsert on case_number).

Usage:  python -m etl.load                 # load all files in data/raw/lca/
        python -m etl.load --file path.csv
"""
from __future__ import annotations

import argparse
import re
import uuid
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse.duckdb"
RAW_LCA = ROOT / "data" / "raw" / "lca"

# Company suffixes stripped when normalizing employer names for dedup
_SUFFIXES = re.compile(
    r"\b(INC|INCORPORATED|LLC|L\.L\.C|LLP|L\.L\.P|LTD|LIMITED|CORP|CORPORATION|CO|COMPANY|PLC|PC|USA?|US)\b\.?",
)
_PUNCT = re.compile(r"[^\w\s]")
_UNIV = re.compile(r"\b(?:UNIVERSITY|COLLEGE|INSTITUTE OF TECHNOLOGY|SCHOOL OF MEDICINE)\b")

JOB_CATEGORY_RULES = [
    (re.compile(r"\b(AI|ARTIFICIAL INTELLIGENCE|MACHINE LEARNING|ML|DEEP LEARNING)\b"), "AI/ML"),
    (re.compile(r"\bDATA (ENGINEER|SCIENTIST|ANALYST|ARCHITECT)\b"), "Data"),
    (re.compile(r"\b(SOFTWARE|DEVELOPER|SDE|PROGRAMMER|FULL ?STACK|FRONTEND|BACKEND)\b"), "Software"),
    (re.compile(r"\b(SECURITY|NETWORK|SYSTEMS?|CLOUD|DEVOPS|SRE|DATABASE)\b"), "Other IT"),
    (re.compile(r"\bENGINEER\b"), "Other Engineering"),
]


def clean_employer(name: str) -> str:
    s = _PUNCT.sub(" ", str(name).upper())
    s = _SUFFIXES.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def job_category(title: str, soc_title: str) -> str:
    text = f"{title} {soc_title}".upper()
    for pattern, cat in JOB_CATEGORY_RULES:
        if pattern.search(text):
            return cat
    return "Other"


def annualize(wage, unit) -> float | None:
    if pd.isna(wage):
        return None
    try:
        w = float(str(wage).replace("$", "").replace(",", ""))
    except ValueError:
        return None
    unit = str(unit or "Year").strip().lower()
    factor = {"year": 1, "hour": 2080, "week": 52, "bi-weekly": 26, "month": 12}.get(unit, 1)
    val = w * factor
    return val if 10_000 <= val <= 5_000_000 else None  # sanity bounds


NEEDED_COLS = {
    "CASE_NUMBER", "CASE_STATUS", "RECEIVED_DATE", "DECISION_DATE", "VISA_CLASS",
    "JOB_TITLE", "SOC_CODE", "SOC_TITLE", "FULL_TIME_POSITION", "EMPLOYER_NAME",
    "EMPLOYER_STATE", "WORKSITE_CITY", "WORKSITE_STATE", "WORKSITE_POSTAL_CODE",
    "WAGE_RATE_OF_PAY_FROM", "WAGE_UNIT_OF_PAY", "PREVAILING_WAGE",
    "PW_UNIT_OF_PAY", "TOTAL_WORKER_POSITIONS",
}


def read_raw(path: Path) -> pd.DataFrame:
    keep = lambda c: str(c).strip().upper() in NEEDED_COLS  # noqa: E731
    if path.suffix.lower() in {".xlsx", ".xls"}:
        try:  # calamine: much faster / lighter on 200MB+ government files
            df = pd.read_excel(path, dtype=str, engine="calamine", usecols=keep)
        except (ImportError, ValueError):
            df = pd.read_excel(path, dtype=str, usecols=keep)
    else:
        df = pd.read_csv(path, dtype=str, low_memory=False, usecols=keep)
    df.columns = [c.strip().upper() for c in df.columns]
    return df


def transform(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    def col(name: str, default=None) -> pd.Series:
        return df[name] if name in df.columns else pd.Series([default] * len(df))

    out = pd.DataFrame({
        "case_number": col("CASE_NUMBER"),
        "case_status": col("CASE_STATUS"),
        "visa_class": col("VISA_CLASS"),
        "received_date": pd.to_datetime(col("RECEIVED_DATE"), errors="coerce").dt.date,
        "decision_date": pd.to_datetime(col("DECISION_DATE"), errors="coerce").dt.date,
        "job_title": col("JOB_TITLE").astype(str).str.strip().str.upper(),
        "soc_code": col("SOC_CODE").astype(str).str.strip(),
        "soc_title": col("SOC_TITLE").astype(str).str.strip(),
        "employer_name": col("EMPLOYER_NAME").astype(str).str.strip(),
        "worksite_city": col("WORKSITE_CITY").astype(str).str.strip().str.upper(),
        "worksite_state": col("WORKSITE_STATE").astype(str).str.strip().str.upper(),
        "worksite_postal_code": col("WORKSITE_POSTAL_CODE").astype(str).str.strip(),
        "full_time": col("FULL_TIME_POSITION").astype(str).str.upper().eq("Y"),
        "total_worker_positions": pd.to_numeric(col("TOTAL_WORKER_POSITIONS"), errors="coerce").fillna(1).astype(int),
    })
    out["annual_wage"] = [annualize(w, u) for w, u in zip(col("WAGE_RATE_OF_PAY_FROM"), col("WAGE_UNIT_OF_PAY"))]
    out["prevailing_wage"] = [annualize(w, u) for w, u in zip(col("PREVAILING_WAGE"), col("PW_UNIT_OF_PAY"))]
    out["wage_unit_raw"] = col("WAGE_UNIT_OF_PAY")
    out["employer_name_clean"] = out["employer_name"].map(clean_employer)
    out["is_university"] = out["employer_name_clean"].str.contains(_UNIV, regex=True, na=False)
    out["job_category"] = [job_category(t, s) for t, s in zip(out["job_title"], out["soc_title"])]
    # fiscal year: US federal FY = Oct 1 - Sep 30
    rd = pd.to_datetime(out["received_date"], errors="coerce")
    out["fiscal_year"] = (rd.dt.year + (rd.dt.month >= 10).astype(int)).astype("Int64")
    out["source_file"] = source_file

    # validation: drop rows missing essential keys, dedupe within file
    out = out.dropna(subset=["case_number", "employer_name"])
    out = out[out["case_number"].str.len() > 5]
    out = out.drop_duplicates(subset=["case_number"], keep="last")
    return out


def load_file(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    run_id = str(uuid.uuid4())
    started = datetime.now()
    try:
        staged = transform(read_raw(path), path.name)
        con.register("staged", staged)

        # dimensions (insert-if-new)
        con.execute("""
            INSERT INTO employers (employer_name, employer_name_clean, is_university, first_seen_date)
            SELECT any_value(employer_name), employer_name_clean, any_value(is_university), min(received_date)
            FROM staged GROUP BY employer_name_clean
            ON CONFLICT (employer_name_clean) DO NOTHING
        """)
        con.execute("""
            INSERT INTO locations (city, state, postal_code)
            SELECT DISTINCT worksite_city, worksite_state, worksite_postal_code FROM staged
            ON CONFLICT DO NOTHING
        """)
        con.execute("""
            INSERT INTO occupations (soc_code, soc_title, job_category)
            SELECT soc_code, any_value(soc_title), any_value(job_category)
            FROM staged GROUP BY soc_code
            ON CONFLICT (soc_code) DO NOTHING
        """)

        # fact upsert
        con.execute("""
            INSERT OR REPLACE INTO lca_filings (
                case_number, case_status, visa_class, received_date, decision_date,
                fiscal_year, employer_id, worksite_location_id, occupation_id,
                job_title, full_time, annual_wage, prevailing_wage, wage_unit_raw,
                total_worker_positions, source_file)
            SELECT s.case_number, s.case_status, s.visa_class, s.received_date, s.decision_date,
                   s.fiscal_year, e.employer_id, l.location_id, o.occupation_id,
                   s.job_title, s.full_time, s.annual_wage, s.prevailing_wage, s.wage_unit_raw,
                   s.total_worker_positions, s.source_file
            FROM staged s
            JOIN employers e ON e.employer_name_clean = s.employer_name_clean
            LEFT JOIN locations l ON l.city = s.worksite_city
                 AND l.state = s.worksite_state AND l.postal_code = s.worksite_postal_code
            LEFT JOIN occupations o ON o.soc_code = s.soc_code
        """)
        n = len(staged)
        con.execute(
            "INSERT INTO etl_runs VALUES (?, 'lca', ?, ?, ?, ?, 'success', NULL)",
            [run_id, path.name, started, datetime.now(), n],
        )
        print(f"  loaded {n:,} rows from {path.name}")
        return n
    except Exception as exc:  # noqa: BLE001
        con.execute(
            "INSERT INTO etl_runs VALUES (?, 'lca', ?, ?, ?, 0, 'failed', ?)",
            [run_id, path.name, started, datetime.now(), str(exc)],
        )
        print(f"  FAILED {path.name}: {exc}")
        raise


def get_connection() -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute(open(ROOT / "sql" / "schema.sql").read())
    return con


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=None)
    args = parser.parse_args()

    con = get_connection()
    files = [args.file] if args.file else sorted(RAW_LCA.glob("*.*"))
    if not files:
        print("No raw files found. Run `python -m etl.sample_data` or `python -m etl.download` first.")
        return
    total = sum(load_file(con, f) for f in files if f.suffix.lower() in {".csv", ".xlsx", ".xls"})
    print(f"Done. {total:,} rows processed -> {DB_PATH}")


if __name__ == "__main__":
    main()
