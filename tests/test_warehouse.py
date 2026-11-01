import shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import duckdb
import pytest
import checks, load
from config import (WAREHOUSE_DB, EXPECTED_TOTALS, EXPECTED_REGIONAL_ROWS_AFTER_AGG,
                    EXPECTED_GEOGRAPHY_ROWS, EXPECTED_DATE_ROWS)

FACT_KEY = {"fact_appointments_monthly": "regional",
            "fact_appointments_by_category": "categories",
            "fact_appointments_by_duration": "duration"}


@pytest.fixture
def con():
    assert WAREHOUSE_DB.exists(), "build the warehouse first: python run_pipeline.py"
    c = duckdb.connect(str(WAREHOUSE_DB), read_only=True)
    yield c
    c.close()


@pytest.fixture
def scratch(tmp_path):
    """A throw-away copy of the warehouse, so tests can break things safely."""
    copy = tmp_path / "copy.duckdb"
    shutil.copy2(WAREHOUSE_DB, copy)
    c = duckdb.connect(str(copy))
    yield c
    c.close()


@pytest.mark.parametrize("table", list(FACT_KEY))
def test_fact_total_equals_constant(con, table):
    total = con.execute(f"SELECT sum(count_of_appointments) FROM {table}").fetchone()[0]
    assert int(total) == EXPECTED_TOTALS[FACT_KEY[table]]


def test_regional_fact_has_expected_rows(con):
    n = con.execute("SELECT count(*) FROM fact_appointments_monthly").fetchone()[0]
    assert n == EXPECTED_REGIONAL_ROWS_AFTER_AGG


@pytest.mark.parametrize("table", ["fact_appointments_by_category", "fact_appointments_by_duration"])
def test_no_orphan_sub_icb_codes(con, table):
    n = con.execute(f"""SELECT count(*) FROM {table} f
        LEFT JOIN dim_geography g ON f.sub_icb_code = g.sub_icb_code WHERE g.sub_icb_code IS NULL""").fetchone()[0]
    assert n == 0


@pytest.mark.parametrize("table,column,dim", [
    ("fact_appointments_monthly", "booking_wait", "dim_booking_wait"),
    ("fact_appointments_by_duration", "duration_band", "dim_duration_band"),
    ("fact_appointments_by_category", "national_category", "dim_national_category"),
])
def test_every_band_label_exists_in_its_dimension(con, table, column, dim):
    n = con.execute(f"""SELECT count(*) FROM {table} f
        LEFT JOIN {dim} d ON f.{column} = d.{column} WHERE d.{column} IS NULL""").fetchone()[0]
    assert n == 0


def test_dim_date_has_one_row_per_day_without_gaps(con):
    n, distinct, first, last = con.execute(
        "SELECT count(*), count(DISTINCT date_key), min(date_key), max(date_key) FROM dim_date").fetchone()
    assert n == distinct == EXPECTED_DATE_ROWS
    assert (last - first).days + 1 == n            # no gaps


def test_dim_geography_has_106_sub_icbs(con):
    assert con.execute("SELECT count(*) FROM dim_geography").fetchone()[0] == EXPECTED_GEOGRAPHY_ROWS


def test_band_dimensions_have_sort_order(con):
    first = con.execute("SELECT booking_wait FROM dim_booking_wait ORDER BY sort_order LIMIT 1").fetchone()[0]
    assert first == "Same Day"


@pytest.mark.parametrize("table", list(FACT_KEY))
def test_loading_the_same_month_twice_changes_nothing(scratch, table):
    month = scratch.execute(f"SELECT max(month_start) FROM {table}").fetchone()[0]
    sql = f"SELECT count(*), sum(count_of_appointments) FROM {table}"
    before = scratch.execute(sql).fetchone()
    load.load_fact_month(scratch, table, month)
    load.load_fact_month(scratch, table, month)
    assert scratch.execute(sql).fetchone() == before


def test_all_nine_checks_pass(con):
    results = checks.run_checks(con)
    failed = [r for r in results if r["status"] != "PASS"]
    assert len(results) == 9 and not failed, failed


def test_a_broken_warehouse_makes_checks_fail(scratch):
    """Prove the checks can fail: remove one month from the category fact."""
    scratch.execute("DELETE FROM fact_appointments_by_category WHERE month_start = DATE '2021-09-01'")
    results = {r["check"]: r["status"] for r in checks.run_checks(scratch)}
    assert results[2] == "FAIL"        # category total no longer matches
    assert results[4] == "FAIL"        # regional and category no longer reconcile
