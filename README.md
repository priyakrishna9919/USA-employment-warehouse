# USA Employment Data Warehouse

A SQL-queryable warehouse of public U.S. employment and visa-sponsorship data, built on DOL OFLC H-1B/LCA disclosure data, with an ETL pipeline, analytical query library, and REST API.

Answers questions like: *Which companies sponsored AI Engineers in California above $170K? Which universities sponsor Software Engineers? Which employers are increasing sponsorship year over year?*

## Architecture

```
DOL / USCIS files ──> etl/download.py ──> data/raw/
                                             │
                      etl/load.py  (clean, normalize wages to annual USD,
                                    dedupe employers, derive job categories,
                                    idempotent upsert on case_number)
                                             │
                                             ▼
                        DuckDB warehouse (data/warehouse.duckdb)
                        star schema: employers / locations / occupations
                                     + lca_filings fact + views
                                             │
              ┌──────────────────────────────┼─────────────────────┐
              ▼                              ▼                     ▼
       sql/queries.sql               api/main.py (FastAPI)    BI tools
       (analyst library)            /sponsors /salary ...    (Metabase etc.)
```

**Why DuckDB?** Zero-setup, single-file, columnar — comfortably handles the full multi-million-row DOL history on a laptop, and the schema ports to PostgreSQL almost unchanged when you want a server.

## Quickstart (60 seconds, no downloads)

```bash
pip install -r requirements.txt
make sample     # synthetic data through the real pipeline
make api        # then open http://127.0.0.1:8000/docs
```

## Loading real government data

1. Visit the DOL OFLC Performance Data page and note the current LCA disclosure file names (they change quarterly): https://www.dol.gov/agencies/eta/foreign-labor/performance
2. Update `config/sources.yaml` with those file names.
3. `make download && make load` (files are 200-700 MB each; the loader streams them fine).
4. USCIS H-1B Employer Data Hub CSVs go in `data/raw/uscis/` (loader for that table is on the roadmap below).

The pipeline is **idempotent** — re-running a file upserts on `case_number`, so scheduled refreshes never create duplicates. Every run is logged to `etl_runs`.

## What the ETL does

- Streams large Excel/CSV files, normalizes headers across fiscal-year format changes
- Converts hourly/weekly/monthly wages to annual USD with sanity bounds ($10K–$5M)
- Normalizes employer names ("Google LLC" = "GOOGLE, INC.") for deduplication
- Flags universities, derives job categories (Software / Data / AI-ML / …) from titles
- Computes federal fiscal year, validates required keys, drops in-file duplicates
- Logs success/failure per file to `etl_runs`

## Interactive dashboard (GitHub Pages, zero servers)

`docs/index.html` is a self-contained dashboard: **DuckDB-WASM runs SQL in your browser** against `docs/data/sponsorships.parquet`. Filters write a live SQL statement you can copy or open in the built-in SQL console.

Local preview: `make dashboard` then open http://localhost:8080
Publish: push to GitHub, then **Settings → Pages → Deploy from a branch → main → /docs**. Your dashboard goes live at `https://<user>.github.io/<repo>/`.

After loading real DOL data, run `python -m etl.export` and commit the refreshed parquet.

## API

`GET /sponsors?title=engineer&state=CA&min_wage=170000&year=2026&category=AI/ML`
`GET /employers?search=amazon` · `GET /salary?group_by=city` · `GET /universities` · `GET /analytics/yoy` · `GET /health`

## Repo layout

```
etl/        download.py · load.py · sample_data.py
sql/        schema.sql · queries.sql (20 analyst queries mapped to the brief)
api/        main.py (FastAPI)
config/     sources.yaml
tests/      test_pipeline.py (unit + end-to-end idempotency)
.github/    CI: tests + pipeline smoke run on every push
```

## Roadmap

1. **PERM loader** — schema table already exists; mirror the LCA transform
2. **USCIS Employer Data Hub loader** — approval/denial stats per employer
3. **BLS OES wages via API** — benchmark offered vs market wages by SOC + area
4. **USAJobs API** — live federal openings joined to occupations
5. **Natural-language querying** — Claude API generates SQL against the schema, executes read-only, explains results
6. **Dashboard** — Metabase or Superset pointed at the DuckDB file (or Postgres)
7. **Orchestration** — the GitHub Actions cron stub in `ci.yml`, or Prefect locally
8. **Scale-out** — swap DuckDB for PostgreSQL + partitioning by fiscal_year when multi-user

## Data source notes

All sources are public U.S. government disclosure data. Respect each portal's terms; avoid scraping sites that prohibit it (the roadmap sticks to official APIs and published files).
