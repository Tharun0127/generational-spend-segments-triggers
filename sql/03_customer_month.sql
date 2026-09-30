-- 03_customer_month.sql
-- One row per customer per calendar month between their first and last transaction.
-- Months with no spend are kept as zeros so volatility and triggers see the gaps.

CREATE OR REPLACE TABLE customer_month AS
WITH tenure AS (
    SELECT customer_id, min(month) AS first_month, max(month) AS last_month
    FROM transactions
    GROUP BY customer_id
),
months AS (
    SELECT DISTINCT month FROM transactions
),
spine AS (
    SELECT t.customer_id, m.month
    FROM tenure t
    JOIN months m ON m.month BETWEEN t.first_month AND t.last_month
),
agg AS (
    SELECT
        customer_id,
        month,
        count(*)                                           AS txns,
        sum(amt)                                           AS spend,
        sum(amt)  FILTER (WHERE category = 'travel')       AS travel_spend,
        count(*)  FILTER (WHERE category = 'travel')       AS travel_txns,
        sum(amt)  FILTER (WHERE category = 'food_dining')  AS dining_spend,
        count(*)  FILTER (WHERE category = 'food_dining')  AS dining_txns
    FROM transactions
    GROUP BY customer_id, month
)
SELECT
    s.customer_id,
    s.month,
    row_number() OVER (PARTITION BY s.customer_id ORDER BY s.month) AS month_idx,
    coalesce(a.txns, 0)          AS txns,
    coalesce(a.spend, 0)         AS spend,
    coalesce(a.travel_spend, 0)  AS travel_spend,
    coalesce(a.travel_txns, 0)   AS travel_txns,
    coalesce(a.dining_spend, 0)  AS dining_spend,
    coalesce(a.dining_txns, 0)   AS dining_txns
FROM spine s
LEFT JOIN agg a USING (customer_id, month);
