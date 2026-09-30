# Data profile

Source: Kaggle `kartik2112/fraud-detection`. Simulated credit card transactions produced by the
Sparkov data generator. This file is written by `src/profile.py` on every rebuild.

## Size and coverage

| file | rows | first_ts | last_ts | fraud_rows |
|---|---|---|---|---|
| fraudTrain.csv | 1,296,675 | 2019-01-01 00:00:18 | 2020-06-21 12:13:37 | 7,506 |
| fraudTest.csv | 555,719 | 2020-06-21 12:14:25 | 2020-12-31 23:59:34 | 2,145 |

- Combined rows: **1,852,394**, all with a distinct `trans_num` (1,852,394).
- Date range: **2019-01-01 to 2020-12-31** (24 calendar months).
- Rows with a null amount, category or dob: 0.
- Fraud rows removed from behavior analysis: **9,651** (0.52% of rows).
- Rows used for behavior analysis: **1,842,743**, total spend $124,663,919.

## Customers

- The data has no customer id. `cc_num` is used as the customer key.
- Distinct cards in the raw data: 999.
- Cards whose every transaction is fraud: 91. They have no legitimate behavior, so they drop out.
- Customers in the analysis: **908**. Cards with exactly one dob, gender and city population: 908.

| generation | customers | share | first_birth_year | last_birth_year | median_monthly_spend |
|---|---|---|---|---|---|
| Silent | 92 | 10.1% | 1924 | 1945 | $3,973 |
| Boomers | 223 | 24.6% | 1946 | 1964 | $3,926 |
| Gen X | 279 | 30.7% | 1965 | 1980 | $5,726 |
| Millennials | 266 | 29.3% | 1981 | 1996 | $6,026 |
| Gen Z | 48 | 5.3% | 1997 | 2005 | $5,878 |

Gen Z has only 48 customers, so every Gen Z estimate is noisy.

## Categories

14 raw merchant categories map to 8 groups. Only grocery, shopping and misc carry a channel tag.

| category | category_group | channel | txns | spend | spend_share | avg_ticket | median_ticket |
|---|---|---|---|---|---|---|---|
| grocery_pos | grocery | in_store | 173,963 | $19,855,279 | 15.9% | $114.14 | $104.52 |
| shopping_pos | shopping | in_store | 165,407 | $12,206,920 | 9.8% | $73.80 | $7.72 |
| gas_transport | gas_transport | untagged | 187,257 | $11,926,125 | 9.6% | $63.69 | $62.94 |
| home | home_kids_pets | untagged | 175,195 | $10,141,466 | 8.1% | $57.89 | $48.16 |
| shopping_net | shopping | online | 137,103 | $9,898,082 | 7.9% | $72.19 | $8.30 |
| kids_pets | home_kids_pets | untagged | 161,423 | $9,298,187 | 7.5% | $57.60 | $47.20 |
| entertainment | dining_entertainment | untagged | 133,826 | $8,455,327 | 6.8% | $63.18 | $50.65 |
| misc_pos | misc | in_store | 113,907 | $7,090,977 | 5.7% | $62.25 | $14.01 |
| food_dining | dining_entertainment | untagged | 130,524 | $6,641,668 | 5.3% | $50.88 | $41.87 |
| health_fitness | health_personal | untagged | 122,368 | $6,624,891 | 5.3% | $54.14 | $42.88 |
| travel | travel | untagged | 57,800 | $6,476,410 | 5.2% | $112.05 | $6.23 |
| misc_net | misc | online | 89,472 | $6,324,752 | 5.1% | $70.69 | $9.73 |
| personal_care | health_personal | untagged | 129,795 | $6,242,739 | 5.0% | $48.10 | $32.79 |
| grocery_net | grocery | online | 64,703 | $3,481,096 | 2.8% | $53.80 | $50.98 |

## Spend distributions

Transaction amount ($), non-fraud rows:

| p01 | p25 | p50 | mean | p75 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|
| 1.26 | 9.61 | 47.24 | 67.65 | 82.56 | 189.59 | 484.91 | 28948.9 |

Amounts are right-skewed (mean well above median), which is why features are log-transformed before clustering.

Per-customer features:

| measure | min | p25 | p50 | mean | p75 | max |
|---|---|---|---|---|---|---|
| Monthly spend ($) | 1391.9 | 3285.8 | 5398.8 | 5720.6 | 7425.0 | 17100.2 |
| Transactions per month | 30.1 | 60.5 | 90.9 | 84.6 | 121.3 | 182.5 |
| Average ticket ($) | 44.0 | 58.1 | 62.5 | 67.6 | 73.9 | 113.9 |
| Recency (days) | 0.0 | 0.0 | 0.0 | 0.1 | 0.0 | 2.0 |

## Things in this data that a real portfolio would not have

These come from the generator and shape every result downstream.

**1. Transaction counts come in fixed tiers.** Every customer makes almost exactly 1, 2, 3, 4, 5 or 6
transactions per day on average over the two years. There is nothing in between.

| txns_per_day_tier | customers | min_txns | max_txns |
|---|---|---|---|
| 1 | 221 | 723 | 730 |
| 2 | 204 | 1,448 | 1,460 |
| 3 | 207 | 2,169 | 2,190 |
| 4 | 152 | 2,895 | 2,920 |
| 5 | 71 | 3,617 | 3,648 |
| 6 | 53 | 4,350 | 4,380 |

**2. Nobody churns or joins.** All 908 customers are active in all 24 months and
recency is 0 to 2 days for everyone. Recency carries
no information here, so it is reported but not used for clustering.

**3. Everyone shares the same seasonality.** December is about twice an average month and January and
February are the lowest. Any trigger that compares a customer with their own previous period will fire
for the whole portfolio after December unless it is measured relative to the portfolio.

| month | txns | spend | active_customers | index_vs_avg |
|---|---|---|---|---|
| 2019-01 | 52,019 | $3,497,970 | 908 | 0.67 |
| 2019-02 | 49,349 | $3,330,611 | 908 | 0.64 |
| 2019-03 | 70,445 | $4,790,249 | 908 | 0.92 |
| 2019-04 | 67,702 | $4,559,437 | 908 | 0.88 |
| 2019-05 | 72,124 | $4,850,354 | 908 | 0.93 |
| 2019-06 | 85,710 | $5,858,193 | 908 | 1.13 |
| 2019-07 | 86,265 | $5,855,325 | 908 | 1.13 |
| 2019-08 | 86,977 | $5,843,338 | 908 | 1.12 |
| 2019-09 | 70,234 | $4,732,159 | 908 | 0.91 |
| 2019-10 | 68,304 | $4,593,528 | 908 | 0.88 |
| 2019-11 | 70,033 | $4,722,945 | 908 | 0.91 |
| 2019-12 | 140,468 | $9,583,022 | 908 | 1.84 |
| 2020-01 | 51,859 | $3,480,469 | 908 | 0.67 |
| 2020-02 | 47,455 | $3,185,994 | 908 | 0.61 |
| 2020-03 | 72,406 | $4,928,026 | 908 | 0.95 |
| 2020-04 | 66,590 | $4,539,156 | 908 | 0.87 |
| 2020-05 | 73,816 | $4,956,810 | 908 | 0.95 |
| 2020-06 | 87,338 | $5,933,018 | 908 | 1.14 |
| 2020-07 | 85,527 | $5,779,543 | 908 | 1.11 |
| 2020-08 | 88,344 | $5,924,693 | 908 | 1.14 |
| 2020-09 | 69,193 | $4,708,299 | 908 | 0.91 |
| 2020-10 | 68,964 | $4,673,380 | 908 | 0.90 |
| 2020-11 | 72,341 | $4,875,406 | 908 | 0.94 |
| 2020-12 | 139,280 | $9,461,994 | 908 | 1.82 |

**4. Time of day is a two-level step.** Transactions are flat within the morning block and flat within
the afternoon and evening block. "Late night" differences between customers reflect how the generator
splits volume between these two blocks.

| block | txns | avg_txns_per_hour |
|---|---|---|
| 00:00 to 11:59 | 721,957 | 60,163 |
| 12:00 to 23:59 | 1,120,786 | 93,399 |

**5. Travel is lumpy.** Most travel transactions are small, and a small number of large ones carry
most of the travel spend.

| ticket | txns | txn_share | spend_share |
|---|---|---|---|
| Under $100 | 49,933 | 86.4% | 4.7% |
| $100 to $499 | 3,851 | 6.7% | 25.2% |
| $500 or more | 4,016 | 6.9% | 70.1% |
