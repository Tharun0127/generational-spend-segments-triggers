-- 04_customer_quarter.sql
-- Quarterly spend per customer with quarter-over-quarter and year-over-year change.
-- LAG(1) is the prior quarter, LAG(4) is the same quarter one year earlier.

CREATE OR REPLACE TABLE customer_quarter AS
WITH q AS (
    SELECT
        customer_id,
        CAST(date_trunc('quarter', month) AS DATE) AS quarter,
        sum(spend)        AS spend,
        sum(txns)         AS txns,
        sum(travel_spend) AS travel_spend,
        sum(dining_spend) AS dining_spend
    FROM customer_month
    GROUP BY 1, 2
),
lagged AS (
    SELECT
        *,
        lag(spend, 1)        OVER w AS prev_q_spend,
        lag(spend, 4)        OVER w AS prev_y_spend,
        lag(travel_spend, 1) OVER w AS prev_q_travel_spend
    FROM q
    WINDOW w AS (PARTITION BY customer_id ORDER BY quarter)
)
SELECT
    *,
    CASE WHEN prev_q_spend > 0 THEN spend / prev_q_spend - 1 END  AS qoq_spend_change,
    CASE WHEN prev_y_spend > 0 THEN spend / prev_y_spend - 1 END  AS yoy_spend_change,
    CASE WHEN prev_q_travel_spend > 0
         THEN travel_spend / prev_q_travel_spend - 1 END          AS qoq_travel_change
FROM lagged;
