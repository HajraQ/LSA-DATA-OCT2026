import json, sys
from datetime import datetime, timezone
import duckdb
from config import (DOCS, WAREHOUSE_DB, EXPECTED_TOTALS, RECONCILE_START, RECONCILE_END, MIN_DURATION_COVERAGE)

FACT_MONTHLY = "fact_appointments_monthly"
FACT_CATEGORY = "fact_appointments_by_category"
FACT_DURATION = "fact_appointments_by_duration"


def _total(con, table):
    return int(con.execute(f"SELECT coalesce(sum(count_of_appointments), 0) FROM {table}").fetchone()[0])


def _transform_total(key):
    path = DOCS / "transform_summary.json"
    if path.exists():
        for r in json.loads(path.read_text()):
            if r["key"] == key:
                return r["total"]
    return None


def check_total(con, table, key):
    got, want, from_transform = _total(con, table), EXPECTED_TOTALS[key], _transform_total(key)
    ok = got == want and (from_transform is None or got == from_transform)
    shown = f"{from_transform:,}" if from_transform is not None else "not available"
    return ok, f"warehouse {got:,} | expected {want:,} | transform output {shown}"


def check_reconcile(con):
    row = con.execute(f"""
        WITH r AS (SELECT month_start, sum(count_of_appointments) AS t FROM {FACT_MONTHLY}
                   WHERE month_start BETWEEN DATE '{RECONCILE_START}' AND DATE '{RECONCILE_END}' GROUP BY 1),
             c AS (SELECT month_start, sum(count_of_appointments) AS t FROM {FACT_CATEGORY}
                   WHERE month_start BETWEEN DATE '{RECONCILE_START}' AND DATE '{RECONCILE_END}' GROUP BY 1)
        SELECT count(*), count(*) FILTER (WHERE r.t IS DISTINCT FROM c.t)
        FROM r FULL JOIN c ON r.month_start = c.month_start""").fetchone()
    months, differ = int(row[0]), int(row[1])
    return months == 11 and differ == 0, f"{differ} of {months} months differ (expected 0 of 11)"


def check_orphans(con):
    n_cat = con.execute(f"""SELECT count(*) FROM {FACT_CATEGORY} f
        LEFT JOIN dim_geography g ON f.sub_icb_code = g.sub_icb_code WHERE g.sub_icb_code IS NULL""").fetchone()[0]
    n_dur = con.execute(f"""SELECT count(*) FROM {FACT_DURATION} f
        LEFT JOIN dim_geography g ON f.sub_icb_code = g.sub_icb_code WHERE g.sub_icb_code IS NULL""").fetchone()[0]
    return n_cat == 0 and n_dur == 0, f"orphan rows: category {n_cat}, duration {n_dur} (expected 0)"


def _unknown_labels(con, table, column, dim):
    rows = con.execute(f"""SELECT f.{column}, count(*) FROM {table} f
        LEFT JOIN {dim} d ON f.{column} = d.{column} WHERE d.{column} IS NULL GROUP BY 1 LIMIT 5""").fetchall()
    n = con.execute(f"""SELECT count(*) FROM {table} f
        LEFT JOIN {dim} d ON f.{column} = d.{column} WHERE d.{column} IS NULL""").fetchone()[0]
    return n == 0, f"{n} rows with an unknown label (expected 0) {[r[0] for r in rows] if n else ''}".strip()


def check_nulls(con):
    n_dates, n_counts = con.execute(f"""SELECT count(*) FILTER (WHERE appointment_date IS NULL),
        count(*) FILTER (WHERE count_of_appointments IS NULL) FROM {FACT_CATEGORY}""").fetchone()
    return n_dates == 0 and n_counts == 0, f"null dates {n_dates}, null counts {n_counts} (expected 0)"


def check_duration_coverage(con):
    rows = con.execute(f"""
        WITH d AS (SELECT month_start, sum(count_of_appointments) AS t FROM {FACT_DURATION} GROUP BY 1),
             c AS (SELECT month_start, sum(count_of_appointments) AS t FROM {FACT_CATEGORY} GROUP BY 1)
        SELECT d.month_start, CAST(d.t AS DOUBLE) / CAST(c.t AS DOUBLE) AS share
        FROM d JOIN c ON d.month_start = c.month_start ORDER BY share""").fetchall()
    if not rows:
        return False, "no months to compare"
    low_month, low = rows[0]
    return low >= MIN_DURATION_COVERAGE, f"lowest {low:.1%} in {str(low_month)[:7]} across {len(rows)} months (need at least {MIN_DURATION_COVERAGE:.0%})"


CHECKS = [
    (1, "fact_appointments_monthly total matches transform total", lambda con: check_total(con, FACT_MONTHLY, "regional")),
    (2, "fact_appointments_by_category total matches transform total", lambda con: check_total(con, FACT_CATEGORY, "categories")),
    (3, "fact_appointments_by_duration total matches transform total", lambda con: check_total(con, FACT_DURATION, "duration")),
    (4, "Regional and category monthly totals reconcile (Aug 2021 - Jun 2022)", check_reconcile),
    (5, "Every sub-ICB code in category and duration facts exists in dim_geography", check_orphans),
    (6, "Every booking-wait label is a known band", lambda con: _unknown_labels(con, FACT_MONTHLY, "booking_wait", "dim_booking_wait")),
    (7, "Every duration label is a known band", lambda con: _unknown_labels(con, FACT_DURATION, "duration_band", "dim_duration_band")),
    (8, "No null dates or counts in the category fact", check_nulls),
    (9, "Duration covers at least 90% of category appointments each month", check_duration_coverage),
]


def run_checks(con):
    """Run EVERY check (one failure never hides the others) and return the results."""
    results = []
    for number, name, fn in CHECKS:
        try:
            ok, detail = fn(con)
        except Exception as err:
            ok, detail = False, f"error while checking: {type(err).__name__}: {err}"
        results.append({"check": number, "name": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    return results


def all_passed(results):
    return all(r["status"] == "PASS" for r in results)


def write_report(results, path=None):
    path = path or (DOCS / "quality_report.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    passed = sum(r["status"] == "PASS" for r in results)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "summary": f"{passed}/{len(results)} passed", "checks": results}
    path.write_text(json.dumps(report, indent=2))
    return path


if __name__ == "__main__":
    con = duckdb.connect(str(WAREHOUSE_DB), read_only=True)
    try:
        results = run_checks(con)
    finally:
        con.close()
    write_report(results)
    for r in results:
        print(f"{r['status']}  {r['check']}. {r['name']}: {r['detail']}")
    sys.exit(0 if all_passed(results) else 2)
