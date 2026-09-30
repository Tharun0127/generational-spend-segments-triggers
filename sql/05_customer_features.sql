-- 05_customer_features.sql
-- One row per customer: RFM, ticket, share of wallet, channel, timing, volatility, trends.

CREATE OR REPLACE TABLE customer_features AS
WITH bounds AS (
    SELECT max(trans_date) AS data_end FROM transactions
),
tx AS (
    SELECT
        customer_id,
        count(*)                          AS n_txns,
        sum(amt)                          AS total_spend,
        avg(amt)                          AS avg_ticket,
        median(amt)                       AS median_ticket,
        max(trans_date)                   AS last_txn_date,
        date_diff('month', min(month), max(month)) + 1 AS active_months,

        -- share of wallet numerators
        sum(amt) FILTER (WHERE category_group = 'travel')               AS spend_travel,
        sum(amt) FILTER (WHERE category_group = 'dining_entertainment') AS spend_dining_entertainment,
        sum(amt) FILTER (WHERE category_group = 'grocery')              AS spend_grocery,
        sum(amt) FILTER (WHERE category_group = 'gas_transport')        AS spend_gas_transport,
        sum(amt) FILTER (WHERE category_group = 'shopping')             AS spend_shopping,
        sum(amt) FILTER (WHERE category_group = 'health_personal')      AS spend_health_personal,
        sum(amt) FILTER (WHERE category_group = 'home_kids_pets')       AS spend_home_kids_pets,
        sum(amt) FILTER (WHERE category_group = 'misc')                 AS spend_misc,

        -- channel (only grocery, shopping and misc are tagged)
        sum(amt) FILTER (WHERE channel = 'online')                      AS spend_online,
        sum(amt) FILTER (WHERE channel IN ('online', 'in_store'))       AS spend_channel_tagged,

        -- timing, as a share of transactions
        avg(CAST(is_weekend AS INTEGER))                                AS weekend_share,
        avg(CAST(is_late_night AS INTEGER))                             AS late_night_share,

        -- benefit-specific inputs used by the targeting score
        sum(amt)  FILTER (WHERE category = 'food_dining')               AS spend_food_dining,
        count(*)  FILTER (WHERE category = 'food_dining')               AS txns_food_dining,
        count(*)  FILTER (WHERE category = 'travel')                    AS txns_travel,
        count(*)  FILTER (WHERE category = 'travel' AND amt >= 100)     AS txns_travel_100plus,
        -- share of calendar years with at least one travel purchase of $100 or more
        count(DISTINCT year(trans_date)) FILTER (WHERE category = 'travel' AND amt >= 100)
            / count(DISTINCT year(trans_date))                          AS travel_active_year_share
    FROM transactions
    GROUP BY customer_id
),
monthly AS (
    SELECT
        customer_id,
        stddev_samp(spend) / nullif(avg(spend), 0)   AS spend_volatility,
        avg(CAST(dining_txns > 0 AS INTEGER))        AS dining_active_month_share,
        avg(CAST(travel_txns > 0 AS INTEGER))        AS travel_active_month_share
    FROM customer_month
    GROUP BY customer_id
),
quarterly AS (
    SELECT
        customer_id,
        avg(qoq_spend_change)                        AS avg_qoq_spend_change,
        arg_max(qoq_spend_change, quarter)           AS last_qoq_spend_change,
        avg(yoy_spend_change)                        AS avg_yoy_spend_change
    FROM customer_quarter
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.generation,
    c.birth_year,
    c.age_at_end,
    c.gender,
    c.city_pop,
    c.city_size_band,

    -- RFM
    date_diff('day', tx.last_txn_date, b.data_end)   AS recency_days,
    tx.active_months,
    tx.n_txns,
    tx.total_spend,
    tx.n_txns      / tx.active_months                AS monthly_txns,
    tx.total_spend / tx.active_months                AS monthly_spend,
    tx.avg_ticket,
    tx.median_ticket,

    -- share of wallet
    coalesce(tx.spend_travel, 0)               / tx.total_spend AS share_travel,
    coalesce(tx.spend_dining_entertainment, 0) / tx.total_spend AS share_dining_entertainment,
    coalesce(tx.spend_grocery, 0)              / tx.total_spend AS share_grocery,
    coalesce(tx.spend_gas_transport, 0)        / tx.total_spend AS share_gas_transport,
    coalesce(tx.spend_shopping, 0)             / tx.total_spend AS share_shopping,
    coalesce(tx.spend_health_personal, 0)      / tx.total_spend AS share_health_personal,
    coalesce(tx.spend_home_kids_pets, 0)       / tx.total_spend AS share_home_kids_pets,
    coalesce(tx.spend_misc, 0)                 / tx.total_spend AS share_misc,

    -- online share of channel-tagged spend
    coalesce(tx.spend_online / nullif(tx.spend_channel_tagged, 0), 0) AS online_share,

    tx.weekend_share,
    tx.late_night_share,
    coalesce(m.spend_volatility, 0)                  AS spend_volatility,

    -- trends
    q.avg_qoq_spend_change,
    q.last_qoq_spend_change,
    q.avg_yoy_spend_change,

    -- benefit inputs
    coalesce(tx.spend_travel, 0)      / tx.active_months AS monthly_travel_spend,
    coalesce(tx.spend_food_dining, 0) / tx.active_months AS monthly_dining_spend,
    tx.txns_food_dining               / tx.active_months AS monthly_dining_txns,
    tx.txns_travel,
    tx.txns_travel_100plus,
    m.dining_active_month_share,
    m.travel_active_month_share,
    tx.travel_active_year_share
FROM customers c
JOIN tx          USING (customer_id)
JOIN monthly m   USING (customer_id)
JOIN quarterly q USING (customer_id)
CROSS JOIN bounds b;
