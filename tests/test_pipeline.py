"""Pipeline tests: run with `pytest -q`."""
from etl.load import annualize, clean_employer, job_category
from etl.sample_data import make_rows
from etl import load as loader


def test_clean_employer_normalizes_suffixes():
    assert clean_employer("Google LLC") == clean_employer("GOOGLE, INC.")
    assert clean_employer("Amazon.com Services LLC") == "AMAZON COM SERVICES"


def test_annualize_units_and_bounds():
    assert annualize("100,000", "Year") == 100000
    assert annualize(50, "Hour") == 50 * 2080
    assert annualize(2, "Hour") is None          # 2*2080 = 4160, below sanity floor
    assert annualize(None, "Year") is None


def test_job_category_rules():
    assert job_category("SENIOR AI ENGINEER", "") == "AI/ML"
    assert job_category("DATA ENGINEER II", "") == "Data"
    assert job_category("SOFTWARE DEVELOPER", "") == "Software"
    assert job_category("SENIOR ACCOUNTANT", "Accountants") == "Other"


def test_transform_dedupes_and_validates():
    import pandas as pd
    df = make_rows(200, seed=1)
    dup = pd.concat([df, df.iloc[[0]]])           # inject duplicate case
    out = loader.transform(dup, "test.csv")
    assert out["case_number"].is_unique
    assert out["fiscal_year"].notna().all()
    assert out["annual_wage"].dropna().between(10_000, 5_000_000).all()


def test_end_to_end_idempotent(tmp_path, monkeypatch):
    import duckdb
    db = tmp_path / "test.duckdb"
    con = duckdb.connect(str(db))
    con.execute(open(loader.ROOT / "sql" / "schema.sql").read())

    raw = tmp_path / "sample.csv"
    make_rows(500, seed=2).to_csv(raw, index=False)

    loader.load_file(con, raw)
    loader.load_file(con, raw)  # second run must not duplicate
    assert con.execute("SELECT COUNT(*) FROM lca_filings").fetchone()[0] == 500
    assert con.execute("SELECT COUNT(*) FROM v_sponsorships").fetchone()[0] == 500
