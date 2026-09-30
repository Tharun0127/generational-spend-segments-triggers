-- 06_triggers.sql
-- Three behavior triggers, evaluated for every customer in every month.
-- Thresholds come in as DuckDB variables (defaults are in src/config.py):
--   travel_drop_pct, travel_min_base, first_travel_min_history,
--   dining_min_base, dining_min_drop, cooldown_months, portfolio_adjust
--
-- portfolio_adjust = 1 measures each customer against what the whole portfolio did over the
-- same months. Without it, shared seasonality (December peak, January trough) fires the
-- drop triggers for almost everyone in Q1. The adjustment only uses data available at the
-- time of the month being scored, so there is no look-ahead.

CREATE OR REPLACE TABLE portfolio_month AS
SELECT
    month,
    sum(travel_spend) AS travel_spend,
    sum(dining_spend) AS dining_spend,
    sum(dining_txns)  AS dining_txns
FROM customer_month
GROUP BY month;

-- ---------------------------------------------------------------------------------------
-- Trigger 1: travel drop.
-- Travel spend in the last 3 months is down more than travel_drop_pct against the 3 months
-- before that, after allowing for the portfolio-wide change over the same windows.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE trigger_travel_drop AS
WITH cust AS (
    SELECT
        customer_id, month, month_idx,
        sum(travel_spend) OVER (
            PARTITION BY customer_id ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS cur_3m
    FROM customer_month
),
cust_lag AS (
    SELECT *, lag(cur_3m, 3) OVER (PARTITION BY customer_id ORDER BY month) AS prior_3m
    FROM cust
),
port AS (
    SELECT
        month,
        sum(travel_spend) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS cur_3m
    FROM portfolio_month
),
port_lag AS (
    SELECT month, cur_3m / nullif(lag(cur_3m, 3) OVER (ORDER BY month), 0) AS portfolio_ratio
    FROM port
),
scored AS (
    SELECT
        c.customer_id, c.month, c.month_idx, c.cur_3m, c.prior_3m,
        c.prior_3m * CASE WHEN getvariable('portfolio_adjust') = 1
                          THEN coalesce(p.portfolio_ratio, 1) ELSE 1 END AS expected_3m
    FROM cust_lag c
    JOIN port_lag p USING (month)
    WHERE c.month_idx >= 6            -- need two full 3-month windows
),
flagged AS (
    SELECT
        *,
        (prior_3m >= getvariable('travel_min_base')
         AND cur_3m < (1 - getvariable('travel_drop_pct')) * expected_3m) AS in_state
    FROM scored
),
with_history AS (
    SELECT
        *,
        max(CASE WHEN in_state THEN month_idx END) OVER (
            PARTITION BY customer_id ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS last_state_idx
    FROM flagged
)
SELECT
    customer_id,
    month,
    'travel_drop'           AS trigger_name,
    prior_3m                AS baseline_value,
    cur_3m                  AS current_value,
    expected_3m - cur_3m    AS spend_at_stake     -- 3-month shortfall against expectation
FROM with_history
WHERE in_state
  AND (last_state_idx IS NULL OR month_idx - last_state_idx > getvariable('cooldown_months'));

-- ---------------------------------------------------------------------------------------
-- Trigger 2: first travel.
-- The customer's first-ever travel transaction, counted only after at least
-- first_travel_min_history months with no travel. Without that guard, every customer's first
-- month in the data would look like a "first" purchase.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE trigger_first_travel AS
WITH first_month AS (
    SELECT customer_id, min(month_idx) FILTER (WHERE travel_txns > 0) AS first_idx
    FROM customer_month
    GROUP BY customer_id
)
SELECT
    cm.customer_id,
    cm.month,
    'first_travel'          AS trigger_name,
    0.0                     AS baseline_value,
    cm.travel_spend         AS current_value,
    cm.travel_spend         AS spend_at_stake     -- the new spend to reinforce
FROM customer_month cm
JOIN first_month f
  ON cm.customer_id = f.customer_id AND cm.month_idx = f.first_idx
WHERE f.first_idx > getvariable('first_travel_min_history');

-- ---------------------------------------------------------------------------------------
-- Trigger 3: dining cooling.
-- Dining transaction count down two months in a row, from a baseline of at least
-- dining_min_base transactions, with a total fall of at least dining_min_drop.
-- With portfolio_adjust = 1 the count is taken as a share of portfolio dining transactions
-- that month, so a month that is slow for everyone does not count as a personal decline.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE trigger_dining_cooling AS
WITH base AS (
    SELECT
        cm.customer_id, cm.month, cm.month_idx, cm.dining_txns, cm.dining_spend,
        CASE WHEN getvariable('portfolio_adjust') = 1
             THEN cm.dining_txns / nullif(p.dining_txns, 0)
             ELSE cm.dining_txns END                                  AS rel_txns,
        CASE WHEN getvariable('portfolio_adjust') = 1
             THEN p.dining_spend ELSE 1 END                           AS portfolio_spend
    FROM customer_month cm
    JOIN portfolio_month p USING (month)
),
lagged AS (
    SELECT
        *,
        lag(rel_txns, 1)        OVER w AS rel_txns_1,
        lag(rel_txns, 2)        OVER w AS rel_txns_2,
        lag(dining_txns, 2)     OVER w AS base_txns,
        lag(dining_spend, 2)    OVER w AS base_spend,
        lag(portfolio_spend, 2) OVER w AS base_portfolio_spend
    FROM base
    WINDOW w AS (PARTITION BY customer_id ORDER BY month)
),
flagged AS (
    SELECT
        *,
        (rel_txns < rel_txns_1
         AND rel_txns_1 < rel_txns_2
         AND base_txns >= getvariable('dining_min_base')
         AND rel_txns <= (1 - getvariable('dining_min_drop')) * rel_txns_2) AS in_state
    FROM lagged
    WHERE month_idx >= 3
),
with_history AS (
    SELECT
        *,
        max(CASE WHEN in_state THEN month_idx END) OVER (
            PARTITION BY customer_id ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS last_state_idx
    FROM flagged
)
SELECT
    customer_id,
    month,
    'dining_cooling'        AS trigger_name,
    CAST(base_txns AS DOUBLE)   AS baseline_value,
    CAST(dining_txns AS DOUBLE) AS current_value,
    -- monthly dining spend shortfall against the baseline month, scaled by the portfolio change
    greatest(base_spend * portfolio_spend / nullif(base_portfolio_spend, 0) - dining_spend, 0) AS spend_at_stake
FROM with_history
WHERE in_state
  AND (last_state_idx IS NULL OR month_idx - last_state_idx > getvariable('cooldown_months'));

CREATE OR REPLACE TABLE trigger_events AS
SELECT * FROM trigger_travel_drop
UNION ALL
SELECT * FROM trigger_first_travel
UNION ALL
SELECT * FROM trigger_dining_cooling;
