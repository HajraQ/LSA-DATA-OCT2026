import csv, json, re, sys
from pathlib import Path
from pyspark.sql import SparkSession, functions as F, types as T
from config import (RAW, CLEAN, DOCS, FILES, DATE_FORMAT, PRIMARY_DATE_COL,
                    EXPECTED_TOTALS, EXPECTED_REGIONAL_ROWS_AFTER_AGG)

CANONICAL = {"other practice staff": "Other Practice Staff"}


def get_spark():
    return (SparkSession.builder.master("local[*]").appName("nhs_transform")
            .config("spark.sql.shuffle.partitions", "8")
            .getOrCreate())


def header(path):
    with open(path, encoding="utf-8-sig", newline="") as f:     # utf-8-sig drops the BOM
        return next(csv.reader(f))


def norm(name):
    return re.sub(r"\W+", "_", name.replace("\ufeff", "").strip()).strip("_").lower()


def transform_file(spark, key):
    path = RAW / FILES[key]["csv"]
    cols = [norm(c) for c in header(path)]
    count_col = [c for c in cols if "count" in c]
    assert len(count_col) == 1, f"{key}: expected one count column, found {count_col}"
    count_col = count_col[0]
    text_cols = [c for c in cols if c != count_col]
    primary = PRIMARY_DATE_COL[key]
    assert primary in cols, f"{key}: date column '{primary}' not in {cols}"

    schema = T.StructType([T.StructField(c, T.LongType() if c == count_col else T.StringType(), True) for c in cols])
    df = spark.read.csv(str(path), header=True, schema=schema, mode="FAILFAST")   # bad rows fail, never become nulls

    # tidy labels in EVERY text column: collapse double spaces, trim, one spelling per label
    for c in text_cols:
        df = df.withColumn(c, F.trim(F.regexp_replace(F.col(c), r"\s+", " ")))
        for lower, proper in CANONICAL.items():
            df = df.withColumn(c, F.when(F.lower(F.col(c)) == lower, proper).otherwise(F.col(c)))

    # new columns beside the originals; ONE date format per file, a wrong value becomes null and is caught below
    parsed = F.try_to_timestamp(F.col(primary), F.lit(DATE_FORMAT[key])).cast("date")
    df = (df.withColumn(primary + "_date", parsed)
            .withColumn("month_start", F.trunc(F.col(primary + "_date"), "month"))
            .withColumn("month", F.date_format(F.col("month_start"), "yyyy-MM")))
    bad = df.filter(F.col("month_start").isNull())
    n_bad = bad.count()
    if n_bad:
        examples = [r[0] for r in bad.select(primary).distinct().limit(5).collect()]
        raise AssertionError(f"{key}: {n_bad} values in '{primary}' do not match {DATE_FORMAT[key]}, e.g. {examples}")

    if key == "regional":      # look-alike rows are real appointments: sum them, never drop
        keys = [c for c in df.columns if c != count_col]
        df = df.groupBy(*keys).agg(F.sum(count_col).alias(count_col)).select(*keys, count_col)

    # checks BEFORE writing, so a wrong number never reaches the Parquet files
    total = df.agg(F.sum(count_col)).first()[0]
    assert total == EXPECTED_TOTALS[key], f"{key}: total {total:,} != expected {EXPECTED_TOTALS[key]:,}"
    assert df.filter(F.col(count_col) <= 0).count() == 0, f"{key}: found counts that are zero or negative"
    if key == "regional":
        n = df.count()
        assert n == EXPECTED_REGIONAL_ROWS_AFTER_AGG, f"regional rows {n:,} != expected {EXPECTED_REGIONAL_ROWS_AFTER_AGG:,}"

    out = CLEAN / key
    df.write.mode("overwrite").partitionBy("month").parquet(str(out))

    back = spark.read.parquet(str(out))
    rows = back.count()
    total_back = back.agg(F.sum(count_col)).first()[0]
    assert total_back == EXPECTED_TOTALS[key], f"{key}: after writing, total {total_back:,} != expected {EXPECTED_TOTALS[key]:,}"
    return {"key": key, "rows": rows, "total": int(total_back), "month_folders": len(list(out.glob("month=*"))),
            "count_col": count_col, "date_col": primary}


def folder_mb(p):
    return sum(f.stat().st_size for f in Path(p).rglob("*") if f.is_file()) / 1e6


def main():
    spark = get_spark()
    spark.sparkContext.setLogLevel("ERROR")
    results = [transform_file(spark, k) for k in FILES]
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "transform_summary.json").write_text(json.dumps(results, indent=2))
    for r in results:
        print(f"{r['key']:11s} rows {r['rows']:>9,}  total {r['total']:>13,}  months {r['month_folders']:>2}  total OK")
    raw_mb = sum((RAW / FILES[k]["csv"]).stat().st_size for k in FILES) / 1e6
    print(f"source CSVs {raw_mb:.1f} MB -> Parquet {folder_mb(CLEAN):.1f} MB")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as err:
        print(f"CHECK FAILED: {err}", file=sys.stderr)
        sys.exit(2)
