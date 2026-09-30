"""Write docs/data_profile.md from the DuckDB tables."""
from __future__ import annotations

import pandas as pd

from . import config, db


def md_table(df: pd.DataFrame, formats: dict | None = None) -> str:
    formats = formats or {}
    cells = df.copy().astype(object)
    for col in df.columns:
        fmt = formats.get(col)
        if fmt:
            cells[col] = [fmt.format(v) for v in df[col]]
    lines = ["| " + " | ".join(str(c) for c in cells.columns) + " |", "|" + "|".join("---" for _ in cells.columns) + "|"]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in cells.itertuples(index=False)]
    return "\n".join(lines)


def run() -> str:
    con = db.connect(read_only=True)
    q = lambda sql: con.execute(sql).df()  # noqa: E731

    files = q("""
        SELECT source_file AS file, count(*) AS rows, min(trans_ts) AS first_ts, max(trans_ts) AS last_ts, sum(is_fraud) AS fraud_rows
        FROM raw_transactions GROUP BY 1 ORDER BY first_ts
    """)
    totals = q("""
        SELECT count(*) AS rows, count(DISTINCT trans_num) AS distinct_trans_num, sum(is_fraud) AS fraud_rows,
               count(DISTINCT cc_num) AS cards,
               min(trans_ts) AS first_ts, max(trans_ts) AS last_ts,
               sum(CASE WHEN amt IS NULL OR category IS NULL OR dob IS NULL THEN 1 ELSE 0 END) AS rows_with_nulls
        FROM raw_transactions
    """).iloc[0]
    fraud_only = q("""
        SELECT count(*) AS n FROM (
            SELECT cc_num FROM raw_transactions GROUP BY 1 HAVING sum(1 - is_fraud) = 0)
    """).iloc[0, 0]
    cust = q("""
        SELECT count(*) AS customers, sum(CAST(attributes_consistent AS INT)) AS consistent FROM customers
    """).iloc[0]
    clean = q("SELECT count(*) AS rows, sum(amt) AS spend, count(DISTINCT month) AS months FROM transactions").iloc[0]

    categories = q("""
        SELECT category, category_group, channel, count(*) AS txns, sum(amt) AS spend,
               sum(amt) / sum(sum(amt)) OVER () AS spend_share, avg(amt) AS avg_ticket, median(amt) AS median_ticket
        FROM transactions GROUP BY 1, 2, 3 ORDER BY spend DESC
    """)
    amt_q = q("""
        SELECT quantile_cont(amt, 0.01) AS p01, quantile_cont(amt, 0.25) AS p25, median(amt) AS p50,
               avg(amt) AS mean, quantile_cont(amt, 0.75) AS p75, quantile_cont(amt, 0.95) AS p95,
               quantile_cont(amt, 0.99) AS p99, max(amt) AS max
        FROM transactions
    """)
    cust_q = q("""
        SELECT 'Monthly spend ($)' AS measure, min(monthly_spend) AS min, quantile_cont(monthly_spend, 0.25) AS p25,
               median(monthly_spend) AS p50, avg(monthly_spend) AS mean, quantile_cont(monthly_spend, 0.75) AS p75,
               max(monthly_spend) AS max FROM customer_features
        UNION ALL
        SELECT 'Transactions per month', min(monthly_txns), quantile_cont(monthly_txns, 0.25), median(monthly_txns),
               avg(monthly_txns), quantile_cont(monthly_txns, 0.75), max(monthly_txns) FROM customer_features
        UNION ALL
        SELECT 'Average ticket ($)', min(avg_ticket), quantile_cont(avg_ticket, 0.25), median(avg_ticket),
               avg(avg_ticket), quantile_cont(avg_ticket, 0.75), max(avg_ticket) FROM customer_features
        UNION ALL
        SELECT 'Recency (days)', min(recency_days), quantile_cont(recency_days, 0.25), median(recency_days),
               avg(recency_days), quantile_cont(recency_days, 0.75), max(recency_days) FROM customer_features
    """)
    gens = q("""
        SELECT generation, count(*) AS customers, count(*) / sum(count(*)) OVER () AS share,
               min(birth_year) AS first_birth_year, max(birth_year) AS last_birth_year,
               median(monthly_spend) AS median_monthly_spend
        FROM customer_features GROUP BY 1 ORDER BY first_birth_year
    """)
    monthly = q("""
        SELECT strftime(month, '%Y-%m') AS month, sum(txns) AS txns, sum(spend) AS spend,
               count(DISTINCT customer_id) FILTER (WHERE txns > 0) AS active_customers
        FROM customer_month GROUP BY 1 ORDER BY 1
    """)
    monthly["index_vs_avg"] = monthly["spend"] / monthly["spend"].mean()
    tiers = q("""
        SELECT CAST(round(n_txns / (active_months * 30.44)) AS INT) AS txns_per_day_tier,
               count(*) AS customers, min(n_txns) AS min_txns, max(n_txns) AS max_txns
        FROM customer_features GROUP BY 1 ORDER BY 1
    """)
    hours = q("""
        SELECT CASE WHEN hour(trans_ts) < 12 THEN '00:00 to 11:59' ELSE '12:00 to 23:59' END AS block,
               count(*) AS txns, count(*) / 12.0 AS avg_txns_per_hour
        FROM transactions GROUP BY 1 ORDER BY 1
    """)
    travel = q("""
        SELECT CASE WHEN amt >= 500 THEN '$500 or more' WHEN amt >= 100 THEN '$100 to $499' ELSE 'Under $100' END AS ticket,
               count(*) AS txns, count(*) / sum(count(*)) OVER () AS txn_share,
               sum(amt) / sum(sum(amt)) OVER () AS spend_share
        FROM transactions WHERE category = 'travel' GROUP BY 1 ORDER BY min(amt)
    """)
    con.close()

    money, count, pct = "${:,.0f}", "{:,.0f}", "{:.1%}"
    doc = f"""# Data profile

Source: Kaggle `{config.KAGGLE_DATASET}`. Simulated credit card transactions produced by the
Sparkov data generator. This file is written by `src/profile.py` on every rebuild.

## Size and coverage

{md_table(files, {"rows": count, "fraud_rows": count})}

- Combined rows: **{totals.rows:,.0f}**, all with a distinct `trans_num` ({totals.distinct_trans_num:,.0f}).
- Date range: **{totals.first_ts:%Y-%m-%d} to {totals.last_ts:%Y-%m-%d}** ({clean.months:.0f} calendar months).
- Rows with a null amount, category or dob: {totals.rows_with_nulls:,.0f}.
- Fraud rows removed from behavior analysis: **{totals.fraud_rows:,.0f}** ({totals.fraud_rows / totals.rows:.2%} of rows).
- Rows used for behavior analysis: **{clean.rows:,.0f}**, total spend ${clean.spend:,.0f}.

## Customers

- The data has no customer id. `cc_num` is used as the customer key.
- Distinct cards in the raw data: {totals.cards:,.0f}.
- Cards whose every transaction is fraud: {fraud_only:,.0f}. They have no legitimate behavior, so they drop out.
- Customers in the analysis: **{cust.customers:,.0f}**. Cards with exactly one dob, gender and city population: {cust.consistent:,.0f}.

{md_table(gens, {"share": pct, "median_monthly_spend": money})}

Gen Z has only {int(gens.loc[gens.generation == "Gen Z", "customers"].iloc[0])} customers, so every Gen Z estimate is noisy.

## Categories

14 raw merchant categories map to 8 groups. Only grocery, shopping and misc carry a channel tag.

{md_table(categories, {"txns": count, "spend": money, "spend_share": pct, "avg_ticket": "${:,.2f}", "median_ticket": "${:,.2f}"})}

## Spend distributions

Transaction amount ($), non-fraud rows:

{md_table(amt_q.round(2))}

Amounts are right-skewed (mean well above median), which is why features are log-transformed before clustering.

Per-customer features:

{md_table(cust_q.round(1))}

## Things in this data that a real portfolio would not have

These come from the generator and shape every result downstream.

**1. Transaction counts come in fixed tiers.** Every customer makes almost exactly 1, 2, 3, 4, 5 or 6
transactions per day on average over the two years. There is nothing in between.

{md_table(tiers, {"customers": count, "min_txns": count, "max_txns": count})}

**2. Nobody churns or joins.** All {cust.customers:,.0f} customers are active in all {clean.months:.0f} months and
recency is 0 to {cust_q.loc[cust_q.measure == "Recency (days)", "max"].iloc[0]:.0f} days for everyone. Recency carries
no information here, so it is reported but not used for clustering.

**3. Everyone shares the same seasonality.** December is about twice an average month and January and
February are the lowest. Any trigger that compares a customer with their own previous period will fire
for the whole portfolio after December unless it is measured relative to the portfolio.

{md_table(monthly, {"txns": count, "spend": money, "active_customers": count, "index_vs_avg": "{:.2f}"})}

**4. Time of day is a two-level step.** Transactions are flat within the morning block and flat within
the afternoon and evening block. "Late night" differences between customers reflect how the generator
splits volume between these two blocks.

{md_table(hours, {"txns": count, "avg_txns_per_hour": count})}

**5. Travel is lumpy.** Most travel transactions are small, and a small number of large ones carry
most of the travel spend.

{md_table(travel, {"txns": count, "txn_share": pct, "spend_share": pct})}
"""
    (config.DOCS_DIR).mkdir(exist_ok=True)
    (config.DOCS_DIR / "data_profile.md").write_text(doc, encoding="utf-8")
    print("Wrote docs/data_profile.md")
    return doc


if __name__ == "__main__":
    run()
