-- 02_transactions.sql
-- Clean transaction table for behavior analysis, plus a customer dimension.
-- Fraud rows are excluded here, so nothing downstream can include them.

CREATE OR REPLACE TABLE transactions AS
SELECT
    trans_num,
    cc_num                                        AS customer_id,
    trans_ts,
    CAST(trans_ts AS DATE)                        AS trans_date,
    CAST(date_trunc('month', trans_ts) AS DATE)   AS month,
    CAST(date_trunc('quarter', trans_ts) AS DATE) AS quarter,
    category,
    CASE
        WHEN category = 'travel'                              THEN 'travel'
        WHEN category IN ('food_dining', 'entertainment')     THEN 'dining_entertainment'
        WHEN category IN ('grocery_pos', 'grocery_net')       THEN 'grocery'
        WHEN category = 'gas_transport'                       THEN 'gas_transport'
        WHEN category IN ('shopping_pos', 'shopping_net')     THEN 'shopping'
        WHEN category IN ('health_fitness', 'personal_care')  THEN 'health_personal'
        WHEN category IN ('home', 'kids_pets')                THEN 'home_kids_pets'
        WHEN category IN ('misc_pos', 'misc_net')             THEN 'misc'
        ELSE 'unmapped'
    END                                           AS category_group,
    -- Only grocery, shopping and misc carry a channel suffix.
    CASE
        WHEN ends_with(category, '_net') THEN 'online'
        WHEN ends_with(category, '_pos') THEN 'in_store'
        ELSE 'untagged'
    END                                           AS channel,
    amt,
    isodow(trans_ts) IN (6, 7)                    AS is_weekend,
    (hour(trans_ts) >= 22 OR hour(trans_ts) < 5)  AS is_late_night
FROM raw_transactions
WHERE is_fraud = 0;

-- One row per customer. cc_num is the customer key (the data has no separate id).
CREATE OR REPLACE TABLE customers AS
WITH base AS (
    SELECT
        cc_num            AS customer_id,
        min(dob)          AS dob,
        min(gender)       AS gender,
        min(city_pop)     AS city_pop,
        count(DISTINCT dob) + count(DISTINCT gender) + count(DISTINCT city_pop) AS n_attr_values
    FROM raw_transactions
    WHERE is_fraud = 0
    GROUP BY cc_num
)
SELECT
    customer_id,
    dob,
    year(dob)             AS birth_year,
    -- Pew Research Center cutoffs
    CASE
        WHEN year(dob) <  1946 THEN 'Silent'
        WHEN year(dob) <= 1964 THEN 'Boomers'
        WHEN year(dob) <= 1980 THEN 'Gen X'
        WHEN year(dob) <= 1996 THEN 'Millennials'
        ELSE 'Gen Z'
    END                   AS generation,
    date_diff('year', dob, (SELECT max(trans_date) FROM transactions)) AS age_at_end,
    gender,
    city_pop,
    CASE
        WHEN city_pop <   2500 THEN '1 Rural (<2.5k)'
        WHEN city_pop <  25000 THEN '2 Small town (2.5k-25k)'
        WHEN city_pop < 250000 THEN '3 Mid city (25k-250k)'
        ELSE '4 Large city (250k+)'
    END                   AS city_size_band,
    -- 3 means exactly one dob, one gender and one city_pop per card
    n_attr_values = 3     AS attributes_consistent
FROM base;
