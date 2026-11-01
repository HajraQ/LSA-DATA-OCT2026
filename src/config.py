import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _path(env_name, default):
    return Path(os.environ.get(env_name, str(default))).resolve()


# Paths live here (or in environment variables). Never hard-code them in other files.
RAW_SRC = _path("LSA_RAW_SRC", "/content")          # where the original files are
RAW = _path("LSA_RAW", ROOT / "data" / "raw")
CLEAN = _path("LSA_CLEAN", ROOT / "data" / "clean")
DOCS = _path("LSA_DOCS", ROOT / "docs")
WAREHOUSE_DB = _path("LSA_WAREHOUSE", ROOT / "warehouse" / "warehouse.duckdb")

# key -> original file name in RAW_SRC, and the CSV used from extract onwards
FILES = {
    "regional":   {"src": "appointments_regional.csv", "csv": "appointments_regional.csv"},
    "categories": {"src": "national_categories.csv",   "csv": "national_categories.csv"},
    "duration":   {"src": "actual_duration.csv.xlsx",  "csv": "actual_duration.csv"},
}

# Date format of each file, stated ONCE. A wrong file fails loudly instead of guessing.
DATE_FORMAT = {"regional": "yyyy-MM", "categories": "dd/MM/yyyy", "duration": "yyyy-MM-dd HH:mm:ss"}
PRIMARY_DATE_COL = {"regional": "appointment_month", "categories": "appointment_date", "duration": "appointment_date"}

# Expected numbers, written as literals on purpose (never "whatever this run produced")
EXPECTED_RAW_ROWS = {596_821, 817_394, 137_793}      # one per file, order not assumed
EXPECTED_TOTALS = {"regional": 742_804_525, "categories": 296_046_770, "duration": 167_980_692}
EXPECTED_REGIONAL_ROWS_AFTER_AGG = 295_692
EXPECTED_GEOGRAPHY_ROWS = 106
EXPECTED_DATE_ROWS = 1096                            # every day 2020-01-01 to 2022-12-31

# Cross-file check window (the only months where both files have data)
RECONCILE_START, RECONCILE_END = "2021-08-01", "2022-06-01"
MIN_DURATION_COVERAGE = 0.90

# Known bands, in the order a chart should show them
BOOKING_WAIT_ORDER = ["Same Day", "1 Day", "2 to 7 Days", "8 to 14 Days", "15 to 21 Days",
                      "22 to 28 Days", "More than 28 Days", "Unknown / Data Quality"]
DURATION_ORDER = ["1-5 Minutes", "6-10 Minutes", "11-15 Minutes", "16-20 Minutes",
                  "21-30 Minutes", "31-60 Minutes", "Unknown / Data Quality"]
