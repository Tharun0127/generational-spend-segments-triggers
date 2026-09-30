"""Paths, constants and thresholds shared by the pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
DB_PATH = PROCESSED_DIR / "spend.duckdb"
SQL_DIR = ROOT / "sql"
OUTPUT_DIR = ROOT / "outputs"
DOCS_DIR = ROOT / "docs"

KAGGLE_DATASET = "kartik2112/fraud-detection"
RAW_FILES = ["fraudTrain.csv", "fraudTest.csv"]

SEED = 42

# Oldest to youngest. The cutoffs themselves live in sql/02_transactions.sql.
GENERATIONS = ["Silent", "Boomers", "Gen X", "Millennials", "Gen Z"]

CATEGORY_GROUPS = {
    "travel": "Travel",
    "dining_entertainment": "Dining and entertainment",
    "grocery": "Grocery",
    "gas_transport": "Gas and transport",
    "shopping": "Shopping",
    "health_personal": "Health and personal care",
    "home_kids_pets": "Home, kids and pets",
    "misc": "Misc",
}
SHARE_COLS = [f"share_{g}" for g in CATEGORY_GROUPS]

# Behavior-only inputs to the clustering. Age, gender and city size are left out on
# purpose so we can test afterwards how much of the segmentation they explain.
# Recency is left out because every customer is active to the end of the data.
CLUSTER_FEATURES = [
    "monthly_spend",
    "monthly_txns",
    "avg_ticket",
    *SHARE_COLS,
    "online_share",
    "weekend_share",
    "late_night_share",
    "spend_volatility",
]

FEATURE_LABELS = {
    "monthly_spend": "Monthly spend ($)",
    "monthly_txns": "Transactions per month",
    "avg_ticket": "Average ticket ($)",
    "median_ticket": "Median ticket ($)",
    "online_share": "Online share of channel-tagged spend",
    "weekend_share": "Weekend share of transactions",
    "late_night_share": "Late-night share of transactions",
    "spend_volatility": "Monthly spend volatility (CV)",
    "avg_yoy_spend_change": "Year-over-year spend change",
    **{f"share_{k}": f"{v} share of wallet" for k, v in CATEGORY_GROUPS.items()},
}

K_RANGE = range(3, 9)
N_BOOTSTRAP = 100
# Chosen after reading outputs/k_selection.csv. The reasoning is in INTERVIEW_PREP.md.
CHOSEN_K = 5

# Trigger thresholds. These are passed to sql/06_triggers.sql as DuckDB variables.
TRIGGER_PARAMS = {
    "travel_drop_pct": 0.50,       # fire when travel spend is down more than this
    "travel_min_base": 200.0,      # prior 3-month travel spend needed before the rule can fire
    "first_travel_min_history": 3, # months of history with no travel before a "first" counts
    "dining_min_base": 4,          # dining transactions in the baseline month
    "dining_min_drop": 0.50,       # total drop over the two months
    "cooldown_months": 2,          # do not re-fire the same trigger within this many months
    "portfolio_adjust": 1,         # 1 = measure changes relative to the portfolio
}
HOLDOUT_SHARE = 0.10
