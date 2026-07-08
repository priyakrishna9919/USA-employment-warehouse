"""REST API over the employment warehouse.

Run:  uvicorn api.main:app --reload
Docs: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from pathlib import Path

import duckdb
from fastapi import FastAPI, HTTPException, Query

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse.duckdb"

app = FastAPI(title="USA Employment Data Warehouse", version="0.1.0")


def q(sql: str, params: list | None = None) -> list[dict]:
    if not DB_PATH.exists():
        raise HTTPException(503, "Warehouse not built yet. Run `make sample` first.")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return con.execute(sql, params or []).df().to_dict(orient="records")
    finally:
        con.close()


@app.get("/health")
def health():
    return {"status": "ok", "rows": q("SELECT COUNT(*) AS n FROM lca_filings")[0]["n"]}


@app.get("/employers")
def employers(search: str | None = None, limit: int = Query(50, le=500)):
    if search:
        return q(
            """SELECT employer_name, fiscal_year, filings, certified, avg_wage, median_wage
               FROM v_employer_yearly WHERE employer_name ILIKE '%' || ? || '%'
               ORDER BY fiscal_year DESC, filings DESC LIMIT ?""",
            [search, limit],
        )
    return q(
        """SELECT employer_name, SUM(filings) AS total_filings, ROUND(AVG(median_wage),0) AS median_wage
           FROM v_employer_yearly GROUP BY 1 ORDER BY total_filings DESC LIMIT ?""",
        [limit],
    )


@app.get("/sponsors")
def sponsors(
    title: str | None = None,
    state: str | None = None,
    min_wage: float | None = None,
    year: int | None = None,
    category: str | None = None,
    limit: int = Query(100, le=1000),
):
    """Filterable sponsorship search - the workhorse endpoint."""
    sql = "SELECT * FROM v_sponsorships WHERE 1=1"
    params: list = []
    if title:
        sql += " AND job_title ILIKE '%' || ? || '%'"; params.append(title)
    if state:
        sql += " AND worksite_state = ?"; params.append(state.upper())
    if min_wage is not None:
        sql += " AND annual_wage >= ?"; params.append(min_wage)
    if year:
        sql += " AND fiscal_year = ?"; params.append(year)
    if category:
        sql += " AND job_category = ?"; params.append(category)
    sql += " ORDER BY annual_wage DESC NULLS LAST LIMIT ?"
    params.append(limit)
    return q(sql, params)


@app.get("/salary")
def salary(group_by: str = Query("state", pattern="^(state|city|employer|occupation)$")):
    col = {
        "state": "worksite_state",
        "city": "worksite_city || ', ' || worksite_state",
        "employer": "employer_name",
        "occupation": "soc_title",
    }[group_by]
    return q(f"""
        SELECT {col} AS grp, COUNT(*) AS filings,
               ROUND(AVG(annual_wage), 0) AS avg_wage,
               ROUND(MEDIAN(annual_wage), 0) AS median_wage
        FROM v_sponsorships WHERE annual_wage IS NOT NULL
        GROUP BY 1 HAVING COUNT(*) >= 5 ORDER BY median_wage DESC LIMIT 200
    """)


@app.get("/universities")
def universities(limit: int = Query(100, le=500)):
    return q(
        """SELECT employer_name, COUNT(*) AS filings, ROUND(MEDIAN(annual_wage),0) AS median_wage
           FROM v_sponsorships WHERE is_university
           GROUP BY 1 ORDER BY filings DESC LIMIT ?""",
        [limit],
    )


@app.get("/analytics/yoy")
def yoy_growth(limit: int = Query(50, le=500)):
    return q(
        """WITH yearly AS (
             SELECT employer_name, fiscal_year, COUNT(*) AS filings
             FROM v_sponsorships GROUP BY 1, 2)
           SELECT employer_name, fiscal_year, filings,
                  filings - LAG(filings) OVER (PARTITION BY employer_name ORDER BY fiscal_year) AS yoy_change
           FROM yearly QUALIFY yoy_change IS NOT NULL
           ORDER BY yoy_change DESC LIMIT ?""",
        [limit],
    )
