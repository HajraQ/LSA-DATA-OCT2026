"""Extract step: copy the raw files into data/raw/, convert the Excel file
to CSV, and write manifest.json describing what was extracted.

Raw files are never edited. Everything later can be rebuilt from here.
"""
import csv
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# Where the original files are (change with SOURCE_DIR if yours differ)
SOURCE_DIR = Path(os.environ.get("SOURCE_DIR", "/content/drive/MyDrive/LSA_Oct2026/raw"))
# Where the raw copy goes (git-ignored)
RAW_DIR = Path(os.environ.get("RAW_DIR", ROOT / "data" / "raw"))

CSV_FILES = ["appointments_regional.csv", "national_categories.csv"]
EXCEL_FILE = "actual_duration.csv.xlsx"     # really Excel, despite the name
DURATION_CSV = "actual_duration.csv"

EXPECTED_ROWS = {
    "appointments_regional.csv": 596_821,
    "national_categories.csv": 817_394,
    "actual_duration.csv": 137_793,
}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def count_csv_rows(path):
    """Data rows, not counting the header. utf-8-sig ignores a BOM."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def entry(path, extracted_at, **extra):
    return {
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_of(path),
        "row_count": count_csv_rows(path),
        "extracted_at": extracted_at,
        **extra,
    }


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    files = []

    # 1. Copy the two CSV files unchanged
    for name in CSV_FILES:
        shutil.copy2(SOURCE_DIR / name, RAW_DIR / name)
        files.append(entry(RAW_DIR / name, now))

    # 2. Copy the Excel file unchanged, then convert it to CSV
    shutil.copy2(SOURCE_DIR / EXCEL_FILE, RAW_DIR / EXCEL_FILE)
    pd.read_excel(RAW_DIR / EXCEL_FILE).to_csv(RAW_DIR / DURATION_CSV, index=False)
    files.append(entry(RAW_DIR / DURATION_CSV, now,
                       converted_from=EXCEL_FILE,
                       source_sha256=sha256_of(RAW_DIR / EXCEL_FILE)))

    # 3. Check row counts against the known values
    for f in files:
        expected = EXPECTED_ROWS[f["file"]]
        status = "OK" if f["row_count"] == expected else "MISMATCH"
        print(f"{f['file']}: rows={f['row_count']:,} -> {status}")
        if status == "MISMATCH":
            raise ValueError(f"{f['file']}: expected {expected:,} rows")

    # 4. Write the manifest
    with open(RAW_DIR / "manifest.json", "w") as fh:
        json.dump({"extracted_at": now, "files": files}, fh, indent=2)
    print(f"manifest written to {RAW_DIR / 'manifest.json'}")


if __name__ == "__main__":
    main()