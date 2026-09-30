"""Load everything in outputs/ into one dictionary for the charts, report and notebook."""
from __future__ import annotations

import json

import pandas as pd

from . import config


def load_all() -> dict:
    out = config.OUTPUT_DIR
    csv = lambda name, **kw: pd.read_csv(out / name, **kw)  # noqa: E731
    js = lambda name: json.loads((out / name).read_text(encoding="utf-8"))  # noqa: E731

    assignments = csv("segment_assignments.csv")
    buckets = csv("customer_generator_buckets.csv")
    features = (
        pd.read_parquet(out / "customer_features.parquet")
        .merge(assignments[["customer_id", "segment_id", "segment_name"]], on="customer_id")
        .merge(buckets, on="customer_id")
    )
    generation = js("generation_insights.json")
    return {
        "features": features,
        "gen_summary": csv("generation_summary.csv"),
        "gen_tests": csv("generation_tests.csv"),
        "insights": generation["insights"],
        "artifact": generation["artifact_check"],
        "k_table": csv("k_selection.csv"),
        "profiles": csv("segment_profiles.csv"),
        "check": js("generator_check.json"),
        "targeting": csv("targeting_scores.csv"),
        "trig_events": csv("trigger_events.csv", parse_dates=["month"]),
        "trig_monthly": csv("trigger_backtest_monthly.csv", parse_dates=["month"]),
        "trig_unadjusted": csv("trigger_backtest_monthly_unadjusted.csv", parse_dates=["month"]),
        "trig_summary": csv("trigger_summary.csv"),
        "trig_overlap": csv("trigger_overlap.csv"),
        "trig_placebo": csv("trigger_placebo_test.csv"),
        "trig_follow_up": csv("trigger_follow_up.csv"),
        "trig_holdout": csv("trigger_holdout_design.csv"),
        "trig_by_segment": csv("trigger_by_segment.csv"),
        "trig_sensitivity": csv("trigger_sensitivity.csv"),
        "trig_params": js("trigger_params.json"),
    }
