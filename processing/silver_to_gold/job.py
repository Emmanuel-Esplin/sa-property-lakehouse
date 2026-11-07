"""Glue job: build the gold Iceberg tables and export a Parquet copy for checking."""

from processing.lake import glue_session, job_argument, table
from processing.silver_to_gold.marts import build_marts


def main() -> None:
    bucket = job_argument("LAKE_BUCKET")
    spark = glue_session(bucket, "silver-to-gold")
    spark.table(table("silver_retail_trade")).createOrReplaceTempView("stg_retail")
    spark.table(table("silver_cpi")).createOrReplaceTempView("stg_cpi")

    for name, frame in build_marts(spark).items():
        frame.writeTo(table(name)).using("iceberg").createOrReplace()
        spark.table(table(name)).coalesce(1).write.mode("overwrite").parquet(
            f"s3://{bucket}/exports/gold/{name}/"
        )
        print(f"GOLD {name}={spark.table(table(name)).count()}")
    spark.stop()


if __name__ == "__main__":
    main()
