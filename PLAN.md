# Plan: Generational Spend Segments and Targeting Triggers

## Business question

How do cardholders differ by generation and by behavior, which segments should get which
benefit offers, and which behavior changes should trigger outreach?

## Data

Kaggle `kartik2112/fraud-detection` (fraudTrain.csv + fraudTest.csv). Simulated card
transactions for 2019 and 2020. Both files are combined. Fraud rows (`is_fraud = 1`) are
dropped from all behavior analysis. `data/raw/` is git-ignored.

## Honesty rules that shape every step

1. The data is synthetic. A generator (Sparkov) assigns each customer to a profile built
   from age band, gender and city size. Any segment I find may simply be that profile.
   I test this directly and report the result whatever it is.
2. There are roughly 1,000 cardholders. Small generations (Gen Z, Silent) will have wide
   intervals. I report group sizes next to every comparison.
3. Effect sizes go next to every p-value: epsilon squared for Kruskal-Wallis, Cramer's V
   for chi-square, and eta squared for the generator-bucket check.
4. No causal claims. The trigger backtest shows who would have fired, not what an offer
   would have done. Lift needs a holdout, which I design but cannot run.

## Steps and commits

| # | Step | Main outputs | Commit |
|---|------|--------------|--------|
| 0 | Scaffold: plan, venv, pinned requirements, .gitignore | PLAN.md, requirements.txt | `Add plan and project scaffold` |
| 1 | Download and profile | src/download.py, src/profile.py, docs/data_profile.md | `Add data download and profile` |
| 2 | SQL features in DuckDB | sql/01..05, src/features.py, outputs/customer_features.parquet | `Add SQL feature engineering` |
| 3 | Generational insights | src/generations.py, outputs/generation_tests.csv | `Add generational comparison with effect sizes` |
| 4 | Segmentation | src/segmentation.py, outputs/segment_*.csv | `Add segmentation with stability and generator check` |
| 5 | Targeting score | src/targeting.py, outputs/targeting_scores.csv | `Add benefit targeting score` |
| 6 | Triggers and backtest | sql/06_triggers.sql, src/triggers.py, outputs/trigger_*.csv | `Add trigger rules and monthly backtest` |
| 7 | Tests | tests/ | `Add tests for feature and trigger logic` |
| 8 | Notebook and HTML report | notebooks/analysis.ipynb, docs/index.html | `Add notebook and interactive report` |
| 9 | Written deliverables | README, targeting playbook | `Add README` |
| 10 | Rebuild from scratch, run tests, fix drift | | `Rebuild from raw and verify` |

## Design decisions

**Customer key.** The dataset has no customer id. `cc_num` is the card number and is used
as the customer key. I check in the profile that each `cc_num` maps to one dob and gender.

**Generations.** Pew cutoffs on birth year: Silent before 1946, Boomers 1946 to 1964,
Gen X 1965 to 1980, Millennials 1981 to 1996, Gen Z 1997 onward.

**Category groups.** The 14 raw categories map to 8 groups:

| Group | Raw categories |
|-------|----------------|
| travel | travel |
| dining_entertainment | food_dining, entertainment |
| grocery | grocery_pos, grocery_net |
| gas_transport | gas_transport |
| shopping | shopping_pos, shopping_net |
| health_personal | health_fitness, personal_care |
| home_kids_pets | home, kids_pets |
| misc | misc_pos, misc_net |

**Online share.** Only four raw categories carry a channel suffix (grocery, shopping, misc
each have `_net` and `_pos`). Online share is `_net` spend divided by `_net + _pos` spend,
so it is measured on the channel-tagged part of the wallet only. This is stated wherever
the number appears.

**Time windows.** Late night is 22:00 to 04:59. Weekend is Saturday and Sunday. Recency is
days from the customer's last transaction to the last date in the data. Frequency and
spend are per active month (months between first and last transaction, inclusive), so
customers with short tenure are not penalised.

**Segmentation inputs.** Behavior only: monthly spend, monthly frequency, average ticket,
the 8 share-of-wallet columns, online share, weekend share, late-night share, volatility.
No age, gender or city size. Those are held out so I can test afterwards how much of the
segmentation they explain.

**Choosing k.** K-means for k = 3 to 8. Silhouette, inertia elbow, bootstrap ARI (100
resamples, compared on the resampled points against the full-data labels), and whether the
segments read as different business stories. A Gaussian mixture on the same features is a
quick second opinion (BIC, and ARI against the K-means labels).

**Generator-bucket check.** For the chosen k: Cramer's V between segment and each of
generation, gender and city-size band; and the cross-validated accuracy of a classifier
that predicts segment from only age, gender and city population, compared with the
majority-class baseline. If the demographics predict the segment well, I say the segments
mostly reproduce generator profiles.

**Targeting score.** For each segment and benefit:

`score = engagement x headroom x value`

- engagement: share of customers in the segment with any spend in the category
- headroom: 1 minus the segment's category share of wallet divided by the highest segment's
  share (room to grow relative to the best segment)
- value: segment mean monthly spend divided by the highest segment's mean monthly spend

Weaknesses are written next to the formula, not hidden.

**Triggers.** Three rules, evaluated monthly or quarterly per customer:

1. Travel drop: travel spend down more than 50% versus the prior quarter, with a minimum
   prior-quarter travel spend so tiny bases do not fire.
2. First travel: the customer's first-ever travel transaction, after at least 3 months of
   history so left-censoring at the start of the data is not mistaken for a first purchase.
3. Dining cooling: dining transaction count down two months in a row.

Backtest per month: customers firing, spend at stake, and pairwise overlap. Each trigger
gets an offer, a channel, a success metric and a 10% randomised holdout design.

## Repo layout

```
data/raw/            git-ignored Kaggle CSVs
data/processed/      git-ignored DuckDB file
sql/                 feature and trigger SQL
src/                 Python pipeline modules
tests/               pytest on small hand-built fixtures
notebooks/           executed narrative notebook
outputs/             small CSV and JSON results (committed, used by docs)
docs/                data_profile.md, index.html, targeting_playbook.md, screenshot
run_all.py           rebuilds everything from raw
```

## Writing rules

Every chart title states the takeaway. Plain words. No em-dashes. Every number in the
README, playbook and resume bullets is read from `outputs/`, never typed from memory.
