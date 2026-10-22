import os
import sys

import pytest
from pyspark.sql import functions as F

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import transform as t

NAMES = ["regional", "categories", "duration"]


@pytest.fixture(scope="session")
def spark():
    s = t.get_spark()
    # Keep appointment_month as text when reading the partition folders back
    s.conf.set("spark.sql.sources.partitionColumnTypeInference.enabled", "false")
    return s


@pytest.fixture(scope="session")
def clean(spark):
    return {n: spark.read.parquet(f"{t.CLEAN}/{n}") for n in NAMES}


@pytest.fixture(scope="session")
def raw(spark):
    reg, cat, dur = t.read_all(spark)
    return {"regional": reg, "categories": cat, "duration": dur}


# ---------- row counts ----------
def test_regional_raw_row_count(raw):
    assert raw["regional"].count() == 596_821


@pytest.mark.parametrize("name", NAMES)
def test_clean_row_counts(clean, name):
    assert clean[name].count() == t.EXPECTED[name][0]


# ---------- totals preserved ----------
@pytest.mark.parametrize("name", NAMES)
def test_clean_totals(clean, name):
    total = clean[name].agg(F.sum("count_of_appointments")).first()[0]
    assert total == t.EXPECTED[name][1]


def test_regional_total_matches_raw(raw, clean):
    raw_total = raw["regional"].agg(F.sum("count_of_appointments")).first()[0]
    clean_total = clean["regional"].agg(F.sum("count_of_appointments")).first()[0]
    assert clean_total == raw_total


# ---------- no duplicate keys ----------
@pytest.mark.parametrize("name", NAMES)
def test_no_duplicate_keys(clean, name):
    df = clean[name]
    keys = [c for c in df.columns if c != "count_of_appointments"]
    assert df.select(keys).distinct().count() == df.count()


# ---------- no double spaces left ----------
@pytest.mark.parametrize("name", NAMES)
def test_no_double_spaces(clean, name):
    df = clean[name]
    for col, dtype in df.dtypes:
        if dtype == "string":
            assert df.filter(F.col(col).contains("  ")).count() == 0, col


def test_hcp_type_values(clean):
    values = {r[0] for r in clean["regional"].select("hcp_type").distinct().collect()}
    assert values == {"GP", "Other Practice Staff", "Unknown"}


# ---------- dates ----------
@pytest.mark.parametrize("name", ["categories", "duration"])
def test_date_month_matches_appointment_month(clean, name):
    df = clean[name]
    assert df.filter(F.col("appointment_date").isNull()).count() == 0
    bad = df.filter(
        F.date_format("appointment_date", "yyyy-MM") != F.col("appointment_month")
    ).count()
    assert bad == 0


def test_regional_month_start(clean):
    df = clean["regional"]
    assert df.filter(F.col("month_start").isNull()).count() == 0
    bad = df.filter(
        F.date_format("month_start", "yyyy-MM") != F.col("appointment_month")
    ).count()
    assert bad == 0


# ---------- counts positive ----------
@pytest.mark.parametrize("name", NAMES)
def test_counts_positive(clean, name):
    df = clean[name]
    assert df.filter(F.col("count_of_appointments").isNull()).count() == 0
    assert df.filter(F.col("count_of_appointments") <= 0).count() == 0


# ---------- no BOM in column names ----------
@pytest.mark.parametrize("name", NAMES)
def test_no_bom_in_columns(clean, name):
    assert not any(c.startswith("\ufeff") for c in clean[name].columns)


# ---------- small tests with made-up rows ----------
def test_categories_day_first_and_code(spark):
    df = spark.createDataFrame(
        [("02/08/2021", "NHS North East and North Cumbria ICB - 00L")],
        ["appointment_date", "sub_icb_location_name"])
    row = t.transform_categories(df).first()
    assert str(row["appointment_date"]) == "2021-08-02"   # 2 August, not 8 February
    assert row["sub_icb_code"] == "00L"


def test_duration_adds_month(spark):
    df = spark.createDataFrame([("2021-12-01",)], ["appointment_date"])
    row = t.transform_duration(df).first()
    assert row["appointment_month"] == "2021-12"


def test_regional_sums_lookalike_rows_and_tidies_labels(spark):
    rows = [
        ("E54000050", "2021-12", "Attended", "Other Practice staff", "Face-to-Face", "15  to 21 Days", 100),
        ("E54000050", "2021-12", "Attended", "Other Practice staff", "Face-to-Face", "15  to 21 Days", 50),
    ]
    df = spark.createDataFrame(rows, t.REGIONAL_SCHEMA)
    out = t.transform_regional(df)
    assert out.count() == 1                                  # two look-alikes became one
    row = out.first()
    assert row["count_of_appointments"] == 150               # summed, not dropped
    assert row["hcp_type"] == "Other Practice Staff"
    assert row["time_between_book_and_appointment"] == "15 to 21 Days"