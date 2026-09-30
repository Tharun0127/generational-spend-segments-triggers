"""Backtest the three triggers month by month and size the holdout test for each."""
from __future__ import annotations

import itertools
import json

import numpy as np
import pandas as pd

from . import config, db

TRIGGERS = ["travel_drop", "first_travel", "dining_cooling"]
TRIGGER_LABELS = {
    "travel_drop": "Travel drop",
    "first_travel": "First travel",
    "dining_cooling": "Dining cooling",
}
# Category spend each trigger is trying to move, used as the holdout outcome.
OUTCOME_COL = {"travel_drop": "travel_spend", "first_travel": "travel_spend", "dining_cooling": "dining_spend"}
N_PLACEBO = 20
Z_ALPHA, Z_POWER = 1.96, 0.84  # two-sided 5% test, 80% power

NAIVE_PARAMS = {
    "portfolio_adjust": 0,
    "travel_min_base": 0.01,
    "dining_min_base": 1,
    "dining_min_drop": 0.0,
    "cooldown_months": 0,
}
DROP_TRIGGERS = ["travel_drop", "dining_cooling"]
# variant label: (parameter overrides, triggers the variant can change)
SENSITIVITY = {
    "Naive rule (no portfolio adjustment, no floors, no cooldown)": (NAIVE_PARAMS, DROP_TRIGGERS),
    "Default without portfolio adjustment": ({"portfolio_adjust": 0}, DROP_TRIGGERS),
    "Default": ({}, TRIGGERS),
    "Travel base $500": ({"travel_min_base": 500.0}, ["travel_drop"]),
    "Travel base $1,000": ({"travel_min_base": 1000.0}, ["travel_drop"]),
    "Dining base 6 transactions": ({"dining_min_base": 6}, ["dining_cooling"]),
    "First travel after 6 months of history": ({"first_travel_min_history": 6}, ["first_travel"]),
}


def fetch_events(con, params: dict | None = None) -> pd.DataFrame:
    db.build_triggers(con, params)
    events = con.execute("SELECT * FROM trigger_events ORDER BY month, trigger_name, customer_id").df()
    events["month"] = pd.to_datetime(events["month"])
    return events


def monthly_backtest(events: pd.DataFrame, months: pd.DatetimeIndex, n_customers: int) -> pd.DataFrame:
    grid = pd.MultiIndex.from_product([months, TRIGGERS], names=["month", "trigger_name"])
    out = (
        events.groupby(["month", "trigger_name"])
        .agg(customers_firing=("customer_id", "nunique"), spend_at_stake=("spend_at_stake", "sum"))
        .reindex(grid, fill_value=0)
        .reset_index()
    )
    out["pct_of_customers"] = out["customers_firing"] / n_customers
    return out


def summarise(events: pd.DataFrame, n_customers: int, n_months: int) -> pd.DataFrame:
    out = events.groupby("trigger_name").agg(
        fires=("customer_id", "size"),
        customers=("customer_id", "nunique"),
        spend_at_stake=("spend_at_stake", "sum"),
        median_stake_per_fire=("spend_at_stake", "median"),
    ).reindex(TRIGGERS, fill_value=0).reset_index()
    out["pct_customers_ever_firing"] = out["customers"] / n_customers
    out["avg_fires_per_month"] = out["fires"] / n_months
    return out


def overlap(events: pd.DataFrame) -> pd.DataFrame:
    """Pairwise overlap: same customer in the same month, and same customer at any time."""
    same_month = {t: set(map(tuple, g[["customer_id", "month"]].to_numpy())) for t, g in events.groupby("trigger_name")}
    ever = {t: set(g["customer_id"]) for t, g in events.groupby("trigger_name")}
    rows = []
    for a, b in itertools.combinations(TRIGGERS, 2):
        ma, mb = same_month.get(a, set()), same_month.get(b, set())
        ea, eb = ever.get(a, set()), ever.get(b, set())
        rows.append({
            "trigger_a": a,
            "trigger_b": b,
            "same_month_both": len(ma & mb),
            "same_month_share_of_smaller": len(ma & mb) / max(1, min(len(ma), len(mb))),
            "customers_ever_both": len(ea & eb),
            "customers_ever_either": len(ea | eb),
            "customer_jaccard": len(ea & eb) / max(1, len(ea | eb)),
        })
    return pd.DataFrame(rows)


def deseasonalise(customer_month: pd.DataFrame) -> pd.DataFrame:
    """Divide each month by the portfolio's index for that month (portfolio month / average month)."""
    out = customer_month.copy()
    for col in ["travel_spend", "dining_spend", "dining_txns"]:
        totals = out.groupby("month")[col].transform("sum")
        index = totals / out.groupby("month")[col].sum().mean()
        out[col] = out[col] / index
    return out


def run_on_frame(customer_month: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Run the trigger SQL against an in-memory copy of customer_month."""
    con = db.connect(":memory:")
    con.register("cm_df", customer_month)
    con.execute("CREATE TABLE customer_month AS SELECT * FROM cm_df")
    events = fetch_events(con, params)
    con.close()
    return events


def placebo_test(customer_month: pd.DataFrame) -> pd.DataFrame:
    """Would the drop triggers fire just as often if each customer's months came in random order?

    Seasonality is removed first, then each customer's months are shuffled. Shuffling keeps
    every customer's level and month-to-month noise but destroys any real sequence such as
    a sustained decline. If the real data fires about as often as the shuffled data, the
    trigger is picking up noise, not behavior change.
    """
    flat = deseasonalise(customer_month)
    params = {"portfolio_adjust": 0}
    actual = run_on_frame(flat, params).groupby("trigger_name").size()

    rng = np.random.default_rng(config.SEED)
    value_cols = ["txns", "spend", "travel_spend", "travel_txns", "dining_spend", "dining_txns"]
    flat = flat.sort_values(["customer_id", "month"]).reset_index(drop=True)
    sizes = flat.groupby("customer_id", sort=False).size().to_numpy()
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
    counts = []
    for _ in range(N_PLACEBO):
        order = np.concatenate([start + rng.permutation(size) for start, size in zip(starts, sizes)])
        shuffled = flat.copy()
        shuffled[value_cols] = flat[value_cols].to_numpy()[order]
        counts.append(run_on_frame(shuffled, params).groupby("trigger_name").size())
    placebo = pd.DataFrame(counts).fillna(0)

    rows = []
    for trig in ["travel_drop", "dining_cooling"]:
        rows.append({
            "trigger_name": trig,
            "actual_fires": int(actual.get(trig, 0)),
            "placebo_fires_mean": float(placebo[trig].mean()),
            "placebo_fires_min": int(placebo[trig].min()),
            "placebo_fires_max": int(placebo[trig].max()),
            "actual_to_placebo_ratio": float(actual.get(trig, 0) / placebo[trig].mean()),
        })
    return pd.DataFrame(rows)


def follow_up(events: pd.DataFrame, customer_month: pd.DataFrame, scope: str = "All customers") -> pd.DataFrame:
    """What happens after a drop trigger fires when nobody sends an offer?

    Uses seasonality-adjusted values, summed over events and indexed to the baseline window.
    Two things to read from it. If the long-run index is far below 1, the baseline was an
    unusual spike, not a habit. If the follow-up index sits above the trigger-period index,
    part of the drop reverses on its own, and a before-and-after comparison of treated
    customers would credit the offer with a recovery that was going to happen anyway.
    """
    flat = deseasonalise(customer_month).sort_values(["customer_id", "month"])
    flat["month"] = pd.to_datetime(flat["month"])
    idx_of = flat.set_index(["customer_id", "month"])["month_idx"]
    specs = {
        # trigger: (column, baseline offsets, trigger-period offsets, follow-up offsets)
        "travel_drop": ("travel_spend", range(-5, -2), range(-2, 1), range(1, 4)),
        "dining_cooling": ("dining_txns", range(-2, -1), range(0, 1), range(1, 3)),
    }
    rows = []
    for trig, (col, base_off, trig_off, next_off) in specs.items():
        wide = flat.pivot(index="customer_id", columns="month_idx", values=col)
        ev = events[events["trigger_name"] == trig]
        windows = []
        for cust, month in zip(ev["customer_id"], ev["month"]):
            i = idx_of[(cust, month)]
            if i + max(next_off) > wide.columns.max():
                continue
            row = wide.loc[cust]
            windows.append([
                row[[i + o for o in base_off]].mean(),
                row[[i + o for o in trig_off]].mean(),
                row[[i + o for o in next_off]].mean(),
                row.mean(),
            ])
        base, trough, after, long_run = np.array(windows).sum(axis=0)
        rows.append({
            "scope": scope,
            "trigger_name": trig,
            "events_with_follow_up": len(windows),
            "baseline_index": 1.0,
            "trigger_period_index": float(trough / base),
            "follow_up_index": float(after / base),
            "long_run_index": float(long_run / base),
            "share_of_drop_recovered_unaided": float((after - trough) / (base - trough)),
        })
    return pd.DataFrame(rows)


def holdout_design(events: pd.DataFrame, customer_month: pd.DataFrame) -> pd.DataFrame:
    """Size a 90/10 treatment and holdout test for each trigger from the backtest.

    Outcome: category spend in the 3 months after the trigger fires.
    Minimum detectable lift is for a two-sided 5% test with 80% power over 12 months of fires.
    """
    cm = customer_month.copy()
    cm["month"] = pd.to_datetime(cm["month"])
    last_month = cm["month"].max()
    rows = []
    for trig in TRIGGERS:
        col = OUTCOME_COL[trig]
        wide = cm.pivot(index="customer_id", columns="month", values=col)
        ev = events[events["trigger_name"] == trig]
        outcomes = []
        for cust, month in zip(ev["customer_id"], ev["month"]):
            window = pd.date_range(month + pd.offsets.MonthBegin(1), periods=3, freq="MS")
            if window[-1] <= last_month:
                outcomes.append(wide.loc[cust, window].sum())
        outcomes = np.array(outcomes)
        fires_per_year = int((ev["month"].dt.year == ev["month"].dt.year.max()).sum())
        n_hold = fires_per_year * config.HOLDOUT_SHARE
        n_treat = fires_per_year - n_hold
        mean, sd = outcomes.mean(), outcomes.std(ddof=1)
        mde = (Z_ALPHA + Z_POWER) * sd * np.sqrt(1 / n_treat + 1 / n_hold)
        # total fires needed to detect a 10% lift with the same 90/10 split
        split_factor = 1 / (1 - config.HOLDOUT_SHARE) + 1 / config.HOLDOUT_SHARE
        n_needed = (Z_ALPHA + Z_POWER) ** 2 * sd**2 * split_factor / (0.10 * mean) ** 2
        rows.append({
            "trigger_name": trig,
            "fires_per_year": fires_per_year,
            "treated": int(round(n_treat)),
            "holdout": int(round(n_hold)),
            "outcome": f"{col} in the 3 months after firing",
            "outcome_mean": float(mean),
            "outcome_sd": float(sd),
            "min_detectable_lift_abs": float(mde),
            "min_detectable_lift_pct": float(mde / mean),
            "fires_needed_for_10pct_lift": int(np.ceil(n_needed)),
        })
    return pd.DataFrame(rows)


def by_segment(events: pd.DataFrame, assignments: pd.DataFrame) -> pd.DataFrame:
    sizes = assignments.groupby("segment_name").size().rename("segment_customers")
    merged = events.merge(assignments[["customer_id", "segment_name"]], on="customer_id")
    out = merged.groupby(["segment_name", "trigger_name"]).agg(
        fires=("customer_id", "size"),
        customers=("customer_id", "nunique"),
        spend_at_stake=("spend_at_stake", "sum"),
    ).reset_index().merge(sizes, on="segment_name")
    out["pct_segment_ever_firing"] = out["customers"] / out["segment_customers"]
    return out


def sensitivity(con) -> pd.DataFrame:
    rows = []
    for label, (params, relevant) in SENSITIVITY.items():
        events = fetch_events(con, params)
        for trig, g in events[events["trigger_name"].isin(relevant)].groupby("trigger_name"):
            rows.append({
                "variant": label,
                "trigger_name": trig,
                "fires": len(g),
                "customers": g["customer_id"].nunique(),
                "share_of_fires_in_jan_to_mar": float(g["month"].dt.month.isin([1, 2, 3]).mean()),
                "peak_month_fires": int(g.groupby("month").size().max()),
            })
    return pd.DataFrame(rows)


def run() -> dict:
    con = db.connect()
    sens = sensitivity(con)
    unadjusted = fetch_events(con, {"portfolio_adjust": 0})
    events = fetch_events(con)  # leaves the default trigger tables in the database
    customer_month = con.execute("SELECT * FROM customer_month").df()
    con.close()
    customer_month["month"] = pd.to_datetime(customer_month["month"])

    n_customers = customer_month["customer_id"].nunique()
    months = pd.DatetimeIndex(sorted(customer_month["month"].unique()))
    assignments = pd.read_csv(config.OUTPUT_DIR / "segment_assignments.csv")
    travelers = assignments.loc[assignments["segment_name"] == "Big-Ticket Travelers", "customer_id"]

    results = {
        "events": events,
        "monthly": monthly_backtest(events, months, n_customers),
        "monthly_unadjusted": monthly_backtest(unadjusted, months, n_customers),
        "summary": summarise(events, n_customers, len(months)),
        "overlap": overlap(events),
        "placebo": placebo_test(customer_month),
        "follow_up": pd.concat([
            follow_up(events, customer_month),
            follow_up(
                events[events["customer_id"].isin(travelers)], customer_month, scope="Big-Ticket Travelers only"
            ),
        ], ignore_index=True),
        "holdout": holdout_design(events, customer_month),
        "by_segment": by_segment(events, assignments),
        "sensitivity": sens,
    }
    names = {
        "events": "trigger_events.csv",
        "monthly": "trigger_backtest_monthly.csv",
        "monthly_unadjusted": "trigger_backtest_monthly_unadjusted.csv",
        "summary": "trigger_summary.csv",
        "overlap": "trigger_overlap.csv",
        "placebo": "trigger_placebo_test.csv",
        "follow_up": "trigger_follow_up.csv",
        "holdout": "trigger_holdout_design.csv",
        "by_segment": "trigger_by_segment.csv",
        "sensitivity": "trigger_sensitivity.csv",
    }
    for key, filename in names.items():
        results[key].to_csv(config.OUTPUT_DIR / filename, index=False, float_format="%.6f")
    (config.OUTPUT_DIR / "trigger_params.json").write_text(
        json.dumps({**config.TRIGGER_PARAMS, "holdout_share": config.HOLDOUT_SHARE}, indent=2), encoding="utf-8"
    )
    s = results["summary"]
    print("Triggers done: " + ", ".join(f"{t} {f} fires" for t, f in zip(s.trigger_name, s.fires)))
    return results


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    out = run()
    for key in ["summary", "overlap", "placebo", "follow_up", "holdout", "by_segment", "sensitivity"]:
        print(f"\n{key}\n{out[key].round(3).to_string()}")
