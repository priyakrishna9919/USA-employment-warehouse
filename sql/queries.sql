-- ============================================================
-- Analytical query library (runs against v_sponsorships / base tables)
-- Each query maps to a real question from the project brief.
-- ============================================================

-- Q1. Which companies sponsored Software Engineers in a given year?
SELECT employer_name, COUNT(*) AS filings
FROM v_sponsorships
WHERE job_title LIKE '%SOFTWARE ENGINEER%' AND fiscal_year = 2026
  AND case_status ILIKE 'Certified%'
GROUP BY 1 ORDER BY filings DESC;

-- Q2. Employers who sponsored H-1B above $180,000
SELECT employer_name, job_title, annual_wage, worksite_city, worksite_state
FROM v_sponsorships
WHERE visa_class = 'H-1B' AND annual_wage > 180000
ORDER BY annual_wage DESC;

-- Q3. Which universities sponsored Software Engineers?
SELECT employer_name, COUNT(*) AS filings, ROUND(AVG(annual_wage), 0) AS avg_wage
FROM v_sponsorships
WHERE is_university AND job_title LIKE '%SOFTWARE ENGINEER%'
GROUP BY 1 ORDER BY filings DESC;

-- Q4. Employers hiring Data Engineers in Ohio
SELECT employer_name, COUNT(*) AS filings, ROUND(MEDIAN(annual_wage), 0) AS median_wage
FROM v_sponsorships
WHERE job_title LIKE '%DATA ENGINEER%' AND worksite_state = 'OH'
GROUP BY 1 ORDER BY filings DESC;

-- Q5. Companies sponsoring AI Engineers in California
SELECT employer_name, COUNT(*) AS filings, ROUND(AVG(annual_wage), 0) AS avg_wage
FROM v_sponsorships
WHERE job_category = 'AI/ML' AND worksite_state = 'CA'
GROUP BY 1 ORDER BY filings DESC;

-- Q6. Employers who filed the most LCAs (all time)
SELECT employer_name, COUNT(*) AS total_filings,
       COUNT(*) FILTER (WHERE case_status ILIKE 'Certified%') AS certified,
       ROUND(100.0 * COUNT(*) FILTER (WHERE case_status ILIKE 'Certified%') / COUNT(*), 1) AS cert_rate_pct
FROM v_sponsorships
GROUP BY 1 ORDER BY total_filings DESC LIMIT 50;

-- Q7. Average salary by state
SELECT worksite_state, COUNT(*) AS filings,
       ROUND(AVG(annual_wage), 0) AS avg_wage, ROUND(MEDIAN(annual_wage), 0) AS median_wage
FROM v_sponsorships
WHERE annual_wage IS NOT NULL
GROUP BY 1 ORDER BY median_wage DESC;

-- Q8. Average salary by city (min 20 filings)
SELECT worksite_city, worksite_state, COUNT(*) AS filings, ROUND(MEDIAN(annual_wage), 0) AS median_wage
FROM v_sponsorships
GROUP BY 1, 2 HAVING COUNT(*) >= 20 ORDER BY median_wage DESC;

-- Q9. Average salary by employer + occupation
SELECT employer_name, soc_title, COUNT(*) AS filings, ROUND(AVG(annual_wage), 0) AS avg_wage
FROM v_sponsorships
GROUP BY 1, 2 HAVING COUNT(*) >= 5 ORDER BY avg_wage DESC;

-- Q10. Companies increasing sponsorship year over year
WITH yearly AS (
  SELECT employer_name, fiscal_year, COUNT(*) AS filings
  FROM v_sponsorships GROUP BY 1, 2
)
SELECT employer_name, fiscal_year, filings,
       filings - LAG(filings) OVER (PARTITION BY employer_name ORDER BY fiscal_year) AS yoy_change
FROM yearly
QUALIFY yoy_change > 0
ORDER BY yoy_change DESC;

-- Q11. Compare two employers head-to-head (Amazon vs Microsoft)
SELECT fiscal_year,
       COUNT(*) FILTER (WHERE employer_name ILIKE '%AMAZON%')    AS amazon,
       COUNT(*) FILTER (WHERE employer_name ILIKE '%MICROSOFT%') AS microsoft
FROM v_sponsorships
GROUP BY 1 ORDER BY 1;

-- Q12. Jobs above a given salary threshold (parameterize :min_wage)
SELECT employer_name, job_title, annual_wage, worksite_city, worksite_state, fiscal_year
FROM v_sponsorships
WHERE annual_wage >= 200000
ORDER BY annual_wage DESC;

-- Q13. Wage premium: offered wage vs prevailing wage by employer
SELECT employer_name, COUNT(*) AS filings,
       ROUND(AVG(annual_wage - prevailing_wage), 0) AS avg_premium
FROM v_sponsorships
WHERE annual_wage IS NOT NULL AND prevailing_wage IS NOT NULL
GROUP BY 1 HAVING COUNT(*) >= 10 ORDER BY avg_premium DESC;

-- Q14. Denial rate by employer (min 20 filings)
SELECT employer_name, COUNT(*) AS filings,
       ROUND(100.0 * COUNT(*) FILTER (WHERE case_status = 'Denied') / COUNT(*), 2) AS denial_rate_pct
FROM v_sponsorships
GROUP BY 1 HAVING COUNT(*) >= 20 ORDER BY denial_rate_pct DESC;

-- Q15. Job category mix per state
SELECT worksite_state, job_category, COUNT(*) AS filings
FROM v_sponsorships
GROUP BY 1, 2 ORDER BY 1, filings DESC;

-- Q16. Top paying occupations (SOC level)
SELECT soc_code, soc_title, COUNT(*) AS filings, ROUND(MEDIAN(annual_wage), 0) AS median_wage
FROM v_sponsorships
GROUP BY 1, 2 HAVING COUNT(*) >= 10 ORDER BY median_wage DESC;

-- Q17. Filing volume trend by month
SELECT date_trunc('month', received_date) AS month, COUNT(*) AS filings
FROM lca_filings GROUP BY 1 ORDER BY 1;

-- Q18. ETL health: recent runs
SELECT * FROM etl_runs ORDER BY started_at DESC LIMIT 20;

-- Q19. University vs corporate wage comparison for the same occupation
SELECT soc_title,
       ROUND(MEDIAN(annual_wage) FILTER (WHERE is_university), 0)     AS university_median,
       ROUND(MEDIAN(annual_wage) FILTER (WHERE NOT is_university), 0) AS corporate_median
FROM v_sponsorships
GROUP BY 1 HAVING COUNT(*) >= 20;

-- Q20. Full-time vs part-time sponsorship share by employer
SELECT employer_name,
       COUNT(*) FILTER (WHERE full_time) AS full_time_n,
       COUNT(*) FILTER (WHERE NOT full_time) AS part_time_n
FROM v_sponsorships
GROUP BY 1 ORDER BY part_time_n DESC LIMIT 25;
