import sys
import duckdb
from config import CLEAN, WAREHOUSE_DB, BOOKING_WAIT_ORDER, DURATION_ORDER


def src(key):
    """Read one of the clean Parquet folders directly, no copying."""
    return f"read_parquet('{CLEAN.as_posix()}/{key}/**/*.parquet', hive_partitioning = true)"


# The sub-ICB code is the last word of the location name: "... ICB - 00L" -> "00L"
SUB_ICB_FROM_NAME = "regexp_extract(sub_icb_location_name, ' - ([A-Za-z0-9]+)$', 1)"

# ---------- dimensions: small description tables, rebuilt on every run ----------
DIM_DDL = {
    "dim_geography": """CREATE TABLE dim_geography (
        sub_icb_code VARCHAR PRIMARY KEY, sub_icb_ons_code VARCHAR, sub_icb_name VARCHAR,
        icb_ons_code VARCHAR, region_ons_code VARCHAR)""",
    "dim_date": """CREATE TABLE dim_date (
        date_key DATE PRIMARY KEY, year_number INTEGER, month_number INTEGER, month_start DATE,
        month_name VARCHAR, weekday_number INTEGER, weekday_name VARCHAR)""",
    "dim_booking_wait": "CREATE TABLE dim_booking_wait (booking_wait VARCHAR PRIMARY KEY, sort_order INTEGER)",
    "dim_duration_band": "CREATE TABLE dim_duration_band (duration_band VARCHAR PRIMARY KEY, sort_order INTEGER)",
    "dim_national_category": "CREATE TABLE dim_national_category (national_category VARCHAR PRIMARY KEY, context_type VARCHAR)",
}

# ---------- facts: tables of numbers, loaded one month at a time ----------
FACT_DDL = [
    """CREATE TABLE IF NOT EXISTS fact_appointments_monthly (
        month_start DATE, icb_code VARCHAR, appointment_status VARCHAR, staff_type VARCHAR,
        appointment_mode VARCHAR, booking_wait VARCHAR, count_of_appointments BIGINT)""",
    """CREATE TABLE IF NOT EXISTS fact_appointments_by_category (
        appointment_date DATE, month_start DATE, sub_icb_code VARCHAR, service_setting VARCHAR,
        national_category VARCHAR, count_of_appointments BIGINT)""",
    """CREATE TABLE IF NOT EXISTS fact_appointments_by_duration (
        appointment_date DATE, month_start DATE, sub_icb_code VARCHAR, duration_band VARCHAR,
        count_of_appointments BIGINT)""",
]

# table -> (clean folder, SELECT list). No GROUP BY and no DISTINCT: the load copies what Week 2 wrote.
FACTS = {
    "fact_appointments_monthly": ("regional", """
        SELECT month_start, icb_ons_code, appointment_status, hcp_type, appointment_mode,
               time_between_book_and_appointment, count_of_appointments"""),
    "fact_appointments_by_category": ("categories", f"""
        SELECT appointment_date_date, month_start, {SUB_ICB_FROM_NAME}, service_setting,
               national_category, count_of_appointments"""),
    "fact_appointments_by_duration": ("duration", """
        SELECT appointment_date_date, month_start, sub_icb_location_code, actual_duration,
               count_of_appointments"""),
}


def load_dimensions(con):
    con.execute("BEGIN")
    try:
        for name, ddl in DIM_DDL.items():
            con.execute(f"DROP TABLE IF EXISTS {name}")
            con.execute(ddl)
        # geography: the duration file has the full set of codes plus ICB and region
        con.execute(f"""INSERT INTO dim_geography
            SELECT DISTINCT sub_icb_location_code, sub_icb_location_ons_code, sub_icb_location_name,
                   icb_ons_code, region_ons_code
            FROM {src('duration')}""")
        # add any sub-ICB that only appears in the category file (code taken from its name)
        con.execute(f"""INSERT INTO dim_geography
            SELECT code, CAST(NULL AS VARCHAR), min(name), min(icb), CAST(NULL AS VARCHAR)
            FROM (SELECT {SUB_ICB_FROM_NAME} AS code, sub_icb_location_name AS name, icb_ons_code AS icb
                  FROM {src('categories')})
            WHERE code <> '' AND code NOT IN (SELECT sub_icb_code FROM dim_geography)
            GROUP BY code""")
        con.execute("""INSERT INTO dim_date
            SELECT CAST(d AS DATE), year(d), month(d), CAST(date_trunc('month', d) AS DATE),
                   monthname(d), isodow(d), dayname(d)
            FROM generate_series(DATE '2020-01-01', DATE '2022-12-31', INTERVAL 1 DAY) AS t(d)""")
        con.executemany("INSERT INTO dim_booking_wait VALUES (?, ?)",
                        [(label, i + 1) for i, label in enumerate(BOOKING_WAIT_ORDER)])
        con.executemany("INSERT INTO dim_duration_band VALUES (?, ?)",
                        [(label, i + 1) for i, label in enumerate(DURATION_ORDER)])
        con.execute(f"""INSERT INTO dim_national_category
            SELECT DISTINCT national_category, context_type FROM {src('categories')}""")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def load_fact_month(con, table, month):
    """Delete this month, then insert this month, in ONE transaction. Safe to run twice."""
    key, select_sql = FACTS[table]
    con.execute("BEGIN")
    try:
        con.execute(f"DELETE FROM {table} WHERE month_start = ?", [month])
        con.execute(f"INSERT INTO {table} {select_sql} FROM {src(key)} WHERE month_start = ?", [month])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def months_in_source(con, key):
    rows = con.execute(f"SELECT DISTINCT month_start FROM {src(key)} ORDER BY 1").fetchall()
    return [r[0] for r in rows]


def summary(con):
    out = {}
    for table in FACTS:
        rows, total = con.execute(f"SELECT count(*), sum(count_of_appointments) FROM {table}").fetchone()
        out[table] = {"rows": int(rows), "total": int(total or 0)}
    for table in DIM_DDL:
        out[table] = {"rows": int(con.execute(f"SELECT count(*) FROM {table}").fetchone()[0])}
    return out


def load_all(db_path):
    con = duckdb.connect(str(db_path))
    try:
        for ddl in FACT_DDL:
            con.execute(ddl)
        load_dimensions(con)
        for table, (key, _) in FACTS.items():
            for month in months_in_source(con, key):
                load_fact_month(con, table, month)
        return summary(con)
    finally:
        con.close()            # always release the file, so nothing stays locked


if __name__ == "__main__":
    WAREHOUSE_DB.parent.mkdir(parents=True, exist_ok=True)
    for name, s in load_all(WAREHOUSE_DB).items():
        print(name, s)
