# NHS GP Appointments Pipeline

A learning project that extracts, cleans and tests NHS England's
"Appointments in General Practice" data using PySpark.

Source: NHS England, Appointments in General Practice
(https://digital.nhs.uk). Licence: check the publication's terms page
(normally Open Government Licence v3.0).

This is a student project. It is not an official NHS product and does
not use NHS logos. The data is not joined with any other data to
identify a practice or an individual.

## What it does

Takes three raw files and turns them into clean, month-partitioned
Parquet files whose totals are checked against known values.

1. **Extract**: the three raw files are placed in `data/raw/` and are
   never edited. The Excel file is converted to CSV.
2. **Transform**: each file is read with an explicit schema, cleaned,
   and written as Parquet partitioned by `appointment_month`.
3. **Check**: after writing, the Parquet files are read back and their
   row counts and totals are compared with expected values.

## The three datasets

| Dataset | Raw file | Raw rows | Clean rows | Total appointments |
|---|---|---|---|---|
| Regional | appointments_regional.csv | 596,821 | 295,692 | 742,804,525 |
| National categories | national_categories.csv | 817,394 | 817,394 | 296,046,770 |
| Actual duration | actual_duration.csv.xlsx | 137,793 | 137,793 | 167,980,692 |

The regional file shrinks because rows that are identical apart from
their count are summed into one row. The total stays the same.

## Data traps found and how they are handled

| Trap | Handling |
|---|---|
| The duration file is named like a CSV but is really Excel | Converted to CSV with pandas before Spark reads it |
| The categories file starts with a hidden byte-order mark (BOM) | Read with a declared schema with clean column names |
| Categories dates are day-first text (02/08/2021 = 2 August) | Parsed with `dd/MM/yyyy` |
| Regional rows that look like duplicates are real appointments | Summed, never dropped |
| Messy labels (double spaces, "Other Practice staff") | Spaces collapsed, one spelling kept |

Every change is explained in [docs/decision_log.md](docs/decision_log.md).

## What the transform adds

- Regional: `month_start` (a real date) beside the text `appointment_month`.
- National categories: `sub_icb_code`, taken from the end of
  `sub_icb_location_name` (for example "... ICB - 00L" gives "00L").
- Actual duration: `appointment_month` (yyyy-MM), created from the date.

Original columns are kept. Counts stay whole numbers.

## Storage size

Source CSV files: 164.8 MB in total.
Clean Parquet (partitioned by appointment_month): 4.8 MB in total.
Parquet is smaller because it compresses each column and stores types.

## Repository layout

```
README.md
requirements.txt
src/
    transform.py     read, clean, write Parquet, check totals
docs/
    decision_log.md  every data change and why
data/raw/            raw files (not committed)
data/clean/          Parquet output (not committed)
```

Data files are never committed. Only code, documents and the manifest
are kept in the repository.

## How to run (Google Colab)

1. Put the three raw files in a Drive folder, with the Excel file
   converted to `actual_duration.csv`.
2. In a notebook, run:

```
!pip install pyspark -q
from google.colab import drive
drive.mount('/content/drive')
```

3. Set the folders if yours differ from the defaults in
   `src/transform.py` (`RAW_DIR` and `CLEAN_DIR`).
4. Run the contents of `src/transform.py`, then call `main()`.

Expected output:

```
regional: rows=295,692 total=742,804,525 -> OK
categories: rows=817,394 total=296,046,770 -> OK
duration: rows=137,793 total=167,980,692 -> OK
```
## How to run the tests

The tests read the clean Parquet files, so run the transform first
(it prints three OK lines), then:

```
pip install pytest
CLEAN_DIR=/path/to/clean python -m pytest -v
```

Expected result: 27 passed. The tests cover row counts, totals
preserved, no duplicate keys, no double spaces, day-first dates,
positive counts, no BOM in column names, and small tests that run
made-up rows through each transform function.
## Status

- [x] Read all three files with explicit schemas
- [x] Clean the regional, categories and duration files
- [x] Write Parquet partitioned by month and check totals
- [ ] pytest test suite (27 tests)
- [ ] Star schema design and load step
- [ ] Dashboard

## A note on scale

The data is about 1.55 million rows and roughly 155 MB, which is small
enough that Spark is not strictly needed. It is used here to learn how
the engine works.
