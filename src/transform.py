from pyspark.sql import SparkSession, functions as F

# Folder holding the raw files (change if yours is different)
RAW = "/content/drive/MyDrive/LSA_Oct2026/raw"

regional_schema = ("icb_ons_code STRING, appointment_month STRING, appointment_status STRING, "
                   "hcp_type STRING, appointment_mode STRING, "
                   "time_between_book_and_appointment STRING, count_of_appointments LONG")

categories_schema = ("appointment_date STRING, icb_ons_code STRING, sub_icb_location_name STRING, "
                     "service_setting STRING, context_type STRING, national_category STRING, "
                     "count_of_appointments LONG, appointment_month STRING")

duration_schema = ("sub_icb_location_code STRING, sub_icb_location_ons_code STRING, "
                   "sub_icb_location_name STRING, icb_ons_code STRING, region_ons_code STRING, "
                   "appointment_date STRING, actual_duration STRING, count_of_appointments LONG")


def get_spark():
    return SparkSession.builder.appName("nhs").getOrCreate()


def read_all(spark):
    reg = spark.read.option("header", True).schema(regional_schema).csv(f"{RAW}/appointments_regional.csv")
    cat = spark.read.option("header", True).schema(categories_schema).csv(f"{RAW}/national_categories.csv")
    dur = spark.read.option("header", True).schema(duration_schema).csv(f"{RAW}/actual_duration.csv")
    return reg, cat, dur


def transform_regional(df):
    out = df
    for c in ["appointment_status", "hcp_type", "appointment_mode",
              "time_between_book_and_appointment"]:
        out = out.withColumn(c, F.trim(F.regexp_replace(F.col(c), r"\s+", " ")))
    out = out.withColumn(
        "hcp_type",
        F.when(F.col("hcp_type") == "Other Practice staff", "Other Practice Staff")
         .otherwise(F.col("hcp_type")))
    out = out.withColumn(
        "month_start", F.to_date(F.concat(F.col("appointment_month"), F.lit("-01"))))
    keys = [c for c in out.columns if c != "count_of_appointments"]
    return out.groupBy(keys).agg(F.sum("count_of_appointments").alias("count_of_appointments"))