"""Generate a realistic synthetic LCA disclosure file so the full pipeline can
be tested without downloading multi-hundred-MB government files.

Column names match the real DOL OFLC LCA disclosure format so transform.py
treats sample and real files identically.

Usage: python -m etl.sample_data [--rows 5000]
"""
from __future__ import annotations

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

EMPLOYERS = [
    ("AMAZON.COM SERVICES LLC", "WA"), ("MICROSOFT CORPORATION", "WA"),
    ("GOOGLE LLC", "CA"), ("META PLATFORMS INC", "CA"),
    ("APPLE INC.", "CA"), ("TATA CONSULTANCY SERVICES LIMITED", "NJ"),
    ("INFOSYS LIMITED", "TX"), ("COGNIZANT TECHNOLOGY SOLUTIONS US CORP", "NJ"),
    ("JPMORGAN CHASE & CO.", "NY"), ("GOLDMAN SACHS & CO. LLC", "NY"),
    ("THE OHIO STATE UNIVERSITY", "OH"), ("CARNEGIE MELLON UNIVERSITY", "PA"),
    ("UNIVERSITY OF CALIFORNIA, BERKELEY", "CA"), ("NVIDIA CORPORATION", "CA"),
    ("DELOITTE CONSULTING LLP", "NY"), ("WALMART INC.", "AR"),
    ("CAPITAL ONE SERVICES, LLC", "VA"), ("ORACLE AMERICA, INC.", "TX"),
]

OCCUPATIONS = [
    ("15-1252", "Software Developers", "SOFTWARE ENGINEER", 110000, 220000),
    ("15-1252", "Software Developers", "SENIOR SOFTWARE ENGINEER", 140000, 260000),
    ("15-2051", "Data Scientists", "DATA SCIENTIST", 105000, 210000),
    ("15-1243", "Database Architects", "DATA ENGINEER", 100000, 200000),
    ("15-2051", "Data Scientists", "MACHINE LEARNING ENGINEER", 130000, 280000),
    ("15-2051", "Data Scientists", "AI ENGINEER", 135000, 300000),
    ("15-1211", "Computer Systems Analysts", "SYSTEMS ANALYST", 80000, 140000),
    ("13-2011", "Accountants and Auditors", "SENIOR ACCOUNTANT", 70000, 120000),
    ("15-1212", "Information Security Analysts", "SECURITY ENGINEER", 110000, 210000),
    ("17-2071", "Electrical Engineers", "ELECTRICAL ENGINEER", 90000, 160000),
]

CITIES = [
    ("SEATTLE", "WA"), ("REDMOND", "WA"), ("MOUNTAIN VIEW", "CA"),
    ("SAN FRANCISCO", "CA"), ("SAN JOSE", "CA"), ("AUSTIN", "TX"),
    ("DALLAS", "TX"), ("NEW YORK", "NY"), ("JERSEY CITY", "NJ"),
    ("COLUMBUS", "OH"), ("PITTSBURGH", "PA"), ("ARLINGTON", "VA"),
    ("BENTONVILLE", "AR"), ("BERKELEY", "CA"), ("CHICAGO", "IL"),
]

STATUSES = ["Certified"] * 90 + ["Denied"] * 3 + ["Withdrawn"] * 4 + ["Certified - Withdrawn"] * 3


def make_rows(n: int, seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        emp, emp_state = rng.choice(EMPLOYERS)
        soc, soc_title, title, lo, hi = rng.choice(OCCUPATIONS)
        city, state = rng.choice(CITIES)
        fy = rng.choice([2023, 2024, 2025, 2026])
        received = date(fy - 1, 10, 1) + timedelta(days=rng.randint(0, 360))
        wage = round(rng.uniform(lo, hi), -3)
        unit = rng.choices(["Year", "Hour"], weights=[95, 5])[0]
        rows.append({
            "CASE_NUMBER": f"I-200-{fy}{i:05d}-{rng.randint(100000, 999999)}",
            "CASE_STATUS": rng.choice(STATUSES),
            "RECEIVED_DATE": received.isoformat(),
            "DECISION_DATE": (received + timedelta(days=rng.randint(3, 60))).isoformat(),
            "VISA_CLASS": rng.choices(["H-1B", "E-3 Australian", "H-1B1 Singapore"], weights=[92, 5, 3])[0],
            "JOB_TITLE": title,
            "SOC_CODE": soc,
            "SOC_TITLE": soc_title,
            "FULL_TIME_POSITION": rng.choices(["Y", "N"], weights=[97, 3])[0],
            "EMPLOYER_NAME": emp,
            "EMPLOYER_STATE": emp_state,
            "WORKSITE_CITY": city,
            "WORKSITE_STATE": state,
            "WORKSITE_POSTAL_CODE": f"{rng.randint(10000, 99999)}",
            "WAGE_RATE_OF_PAY_FROM": wage if unit == "Year" else round(wage / 2080, 2),
            "WAGE_UNIT_OF_PAY": unit,
            "PREVAILING_WAGE": round(wage * rng.uniform(0.8, 0.98), -3) if unit == "Year" else round(wage / 2080 * 0.9, 2),
            "PW_UNIT_OF_PAY": unit,
            "TOTAL_WORKER_POSITIONS": rng.choices([1, 2, 5], weights=[90, 7, 3])[0],
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=5000)
    args = parser.parse_args()
    out = ROOT / "data" / "raw" / "lca" / "LCA_Disclosure_Data_SAMPLE.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    make_rows(args.rows).to_csv(out, index=False)
    print(f"wrote {args.rows} rows -> {out}")


if __name__ == "__main__":
    main()
