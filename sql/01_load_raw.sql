-- 01_load_raw.sql
-- Combine fraudTrain.csv and fraudTest.csv into one raw table.
-- The glob path is passed in as the DuckDB variable raw_glob.

CREATE OR REPLACE TABLE raw_transactions AS
SELECT
    parse_filename(filename) AS source_file,
    trans_num,
    CAST(trans_date_trans_time AS TIMESTAMP) AS trans_ts,
    CAST(cc_num AS BIGINT)                   AS cc_num,
    category,
    CAST(amt AS DOUBLE)                      AS amt,
    gender,
    CAST(city_pop AS BIGINT)                 AS city_pop,
    CAST(dob AS DATE)                        AS dob,
    CAST(is_fraud AS INTEGER)                AS is_fraud
FROM read_csv(getvariable('raw_glob'), header = true, union_by_name = true, filename = true);
