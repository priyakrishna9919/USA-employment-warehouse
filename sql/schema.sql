-- ============================================================
-- USA Employment Data Warehouse - Core Schema (DuckDB)
-- Star schema: dimension tables + fact tables
-- ============================================================

CREATE SEQUENCE IF NOT EXISTS seq_employer START 1;
CREATE SEQUENCE IF NOT EXISTS seq_location START 1;
CREATE SEQUENCE IF NOT EXISTS seq_occupation START 1;

-- ---------- DIMENSIONS ----------

CREATE TABLE IF NOT EXISTS employers (
    employer_id     BIGINT PRIMARY KEY DEFAULT nextval('seq_employer'),
    employer_name   VARCHAR NOT NULL,
    employer_name_clean VARCHAR NOT NULL,   -- normalized for dedup (upper, no punctuation/suffixes)
    naics_code      VARCHAR,
    is_university   BOOLEAN DEFAULT FALSE,  -- heuristic: name contains UNIVERSITY/COLLEGE/INSTITUTE
    first_seen_date DATE,
    UNIQUE (employer_name_clean)
);

CREATE TABLE IF NOT EXISTS locations (
    location_id BIGINT PRIMARY KEY DEFAULT nextval('seq_location'),
    city        VARCHAR,
    state       VARCHAR,        -- 2-letter code
    postal_code VARCHAR,
    UNIQUE (city, state, postal_code)
);

CREATE TABLE IF NOT EXISTS occupations (
    occupation_id BIGINT PRIMARY KEY DEFAULT nextval('seq_occupation'),
    soc_code      VARCHAR NOT NULL,
    soc_title     VARCHAR,
    job_category  VARCHAR,      -- derived: Software, Data, AI/ML, Other STEM, Non-STEM
    UNIQUE (soc_code)
);

-- ---------- FACTS ----------

-- LCA filings (DOL OFLC H-1B / H-1B1 / E-3 disclosure data)
CREATE TABLE IF NOT EXISTS lca_filings (
    case_number        VARCHAR PRIMARY KEY,
    case_status        VARCHAR,             -- Certified, Denied, Withdrawn, Certified-Withdrawn
    visa_class         VARCHAR,             -- H-1B, H-1B1 Chile, H-1B1 Singapore, E-3
    received_date      DATE,
    decision_date      DATE,
    fiscal_year        INTEGER,
    employer_id        BIGINT REFERENCES employers(employer_id),
    worksite_location_id BIGINT REFERENCES locations(location_id),
    occupation_id      BIGINT REFERENCES occupations(occupation_id),
    job_title          VARCHAR,
    full_time          BOOLEAN,
    annual_wage        DOUBLE,              -- normalized to annual USD
    prevailing_wage    DOUBLE,
    wage_unit_raw      VARCHAR,
    total_worker_positions INTEGER DEFAULT 1,
    source_file        VARCHAR,
    loaded_at          TIMESTAMP DEFAULT current_timestamp
);

-- PERM (green card) filings - same dimensional model
CREATE TABLE IF NOT EXISTS perm_filings (
    case_number     VARCHAR PRIMARY KEY,
    case_status     VARCHAR,
    received_date   DATE,
    decision_date   DATE,
    fiscal_year     INTEGER,
    employer_id     BIGINT REFERENCES employers(employer_id),
    worksite_location_id BIGINT REFERENCES locations(location_id),
    occupation_id   BIGINT REFERENCES occupations(occupation_id),
    job_title       VARCHAR,
    annual_wage     DOUBLE,
    source_file     VARCHAR,
    loaded_at       TIMESTAMP DEFAULT current_timestamp
);

-- USCIS H-1B Employer Data Hub (approvals/denials per employer per FY)
CREATE TABLE IF NOT EXISTS uscis_employer_stats (
    fiscal_year   INTEGER,
    employer_id   BIGINT REFERENCES employers(employer_id),
    initial_approvals INTEGER,
    initial_denials   INTEGER,
    continuing_approvals INTEGER,
    continuing_denials   INTEGER,
    PRIMARY KEY (fiscal_year, employer_id)
);

-- ETL bookkeeping
CREATE TABLE IF NOT EXISTS etl_runs (
    run_id      VARCHAR PRIMARY KEY,
    source      VARCHAR,
    file_name   VARCHAR,
    started_at  TIMESTAMP,
    finished_at TIMESTAMP,
    rows_loaded BIGINT,
    status      VARCHAR,   -- success | failed
    error       VARCHAR
);

-- ---------- VIEWS ----------

CREATE OR REPLACE VIEW v_sponsorships AS
SELECT f.case_number, f.case_status, f.visa_class, f.fiscal_year,
       f.job_title, f.annual_wage, f.prevailing_wage, f.full_time,
       e.employer_name, e.is_university,
       o.soc_code, o.soc_title, o.job_category,
       l.city AS worksite_city, l.state AS worksite_state
FROM lca_filings f
JOIN employers e   ON f.employer_id = e.employer_id
LEFT JOIN occupations o ON f.occupation_id = o.occupation_id
LEFT JOIN locations l   ON f.worksite_location_id = l.location_id;

CREATE OR REPLACE VIEW v_employer_yearly AS
SELECT e.employer_name, f.fiscal_year,
       COUNT(*) AS filings,
       COUNT(*) FILTER (WHERE f.case_status ILIKE 'Certified%') AS certified,
       ROUND(AVG(f.annual_wage), 0) AS avg_wage,
       ROUND(MEDIAN(f.annual_wage), 0) AS median_wage
FROM lca_filings f
JOIN employers e ON f.employer_id = e.employer_id
GROUP BY 1, 2;

CREATE OR REPLACE VIEW v_perm AS
SELECT f.case_number, f.case_status, f.fiscal_year, f.job_title, f.annual_wage,
       e.employer_name, e.is_university,
       o.soc_code, o.soc_title, o.job_category,
       l.city AS worksite_city, l.state AS worksite_state
FROM perm_filings f
JOIN employers e   ON f.employer_id = e.employer_id
LEFT JOIN occupations o ON f.occupation_id = o.occupation_id
LEFT JOIN locations l   ON f.worksite_location_id = l.location_id;
