"""Transform step: read the three raw files, clean them, write Parquet.

Raw files are never edited. Output goes to CLEAN, partitioned by month.
"""
import os
from pyspark.sql import SparkSession, functions as F

# Folders (override with environment variables if your paths differ)
RAW = os.environ.get("RAW_DIR", "/content/drive/MyDrive/LSA_Oct2026/raw")
CLEAN = os.environ.get("CLEAN_DIR", "/content/drive/MyDrive/LSA_Oct2026/clean")

# Explicit schemas: names and types are declared, never guessed.
# Dates are read as text and parsed in the transform functions.
# Because we supply the column names, the invisible byte-order mark (BOM)
# in the categories file header never becomes part of a column name.
REGIONAL_SCHEMA = (
    "icb_ons_code STRING, appointment_month STRING, appointment_status STRING, "
    "hcp_type STRING, appointment_mode STRING, "
    "time_between_book_and_appointment STRING, count_of_appointments LONG"
)

CATEGORIES_SCHEMA = (
    "appointment_date STRING, icb_ons_code STRING, sub_icb_location_name STRING, "
    "service_setting STRING, context_type STRING, national_category STRING, "
    "count_of_appointments LONG, appointment_month STRING"
)

DURATION_SCHEMA = (
    "sub_icb_location_code STRING, sub_icb_location_ons_code STRING, "
    "sub_icb_location_name STRING, icb_ons_code STRING, region_ons_code STRING, "
    "appointment_date STRING, actual_duration STRING, count_of_appointments LONG"
)

# Expected (rows, total appointments) after cleaning
EXPECTED = {
    "regional": (295_692, 742_804_525),
    "categories": (817_394, 296_046_770),
    "duration": (137_793, 167_980_692),
}


def get_spark():
    return SparkSession.builder.appName("nhs_gp_transform").getOrCreate()


def read_csv(spark, path, schema):
    return spark.read.option("header", True).schema(schema).csv(path)


def read_all(spark):
    reg = read_csv(spark, f"{RAW}/appointments_regional.csv", REGIONAL_SCHEMA)
    cat = read_csv(spark, f"{RAW}/national_categories.csv", CATEGORIES_SCHEMA)
    dur = read_csv(spark, f"{RAW}/actual_duration.csv", DURATION_SCHEMA)
    return reg, cat, dur


def transform_regional(df):
    out = df
    # Tidy labels: collapse repeated spaces, trim the ends
    for c in ["appointment_status", "hcp_type", "appointment_mode",
              "time_between_book_and_appointment"]:
        out = out.withColumn(c, F.trim(F.regexp_replace(F.col(c), r"\s+", " ")))
    # One spelling of Other Practice Staff
    out = out.withColumn(
        "hcp_type",
        F.when(F.col("hcp_type") == "Other Practice staff", "Other Practice Staff")
         .otherwise(F.col("hcp_type")))
    # Real date column beside the original text month
    out = out.withColumn(
        "month_start", F.to_date(F.concat(F.col("appointment_month"), F.lit("-01"))))
    # Sum look-alike rows (never drop them)
    keys = [c for c in out.columns if c != "count_of_appointments"]
    return out.groupBy(keys).agg(
        F.sum("count_of_appointments").alias("count_of_appointments"))


def transform_categories(df):
    # Dates in this file are day-first text, e.g. 02/08/2021 = 2 August 2021
    out = df.withColumn("appointment_date", F.to_date(F.col("appointment_date"), "dd/MM/yyyy"))
    # Sub-ICB code is the end of the location name: "... ICB - 00L" -> "00L"
    out = out.withColumn(
        "sub_icb_code",
        F.regexp_extract(F.col("sub_icb_location_name"), r"-\s*([A-Za-z0-9]+)\s*$", 1))
    return out


def transform_duration(df):
    # The converted CSV has dates as yyyy-MM-dd
    out = df.withColumn("appointment_date", F.to_date(F.col("appointment_date"), "yyyy-MM-dd"))
    out = out.withColumn("appointment_month", F.date_format(F.col("appointment_date"), "yyyy-MM"))
    return out


def write_parquet(df, name):
    path = f"{CLEAN}/{name}"
    df.write.mode("overwrite").partitionBy("appointment_month").parquet(path)
    return path


def check(name, df):
    rows = df.count()
    total = df.agg(F.sum("count_of_appointments")).first()[0]
    exp_rows, exp_total = EXPECTED[name]
    ok = (rows, total) == (exp_rows, exp_total)
    print(f"{name}: rows={rows:,} total={total:,} -> {'OK' if ok else 'MISMATCH'}")
    if not ok:
        raise ValueError(f"{name}: expected rows={exp_rows:,} total={exp_total:,}")


def main():
    spark = get_spark()
    reg, cat, dur = read_all(spark)

    clean = {
        "regional": transform_regional(reg),
        "categories": transform_categories(cat),
        "duration": transform_duration(dur),
    }
    for name, df in clean.items():
        write_parquet(df, name)

    # Re-read what was written, so the check tests the saved files
    for name in clean:
        check(name, spark.read.parquet(f"{CLEAN}/{name}"))


if __name__ == "__main__":
    main()