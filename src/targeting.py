"""Rank segments for two hypothetical benefits with a transparent score.

score = engagement x headroom x value

engagement  Share of redemption periods in which the segment's customers already make a
            qualifying purchase. Months with any dining transaction for the monthly dining
            credit; years with a travel purchase of $100 or more for the annual travel credit.
headroom    Room to grow category share of wallet. For each customer,
            1 - (category share of wallet / 90th percentile share across all customers),
            clipped to 0..1, then averaged over the segment.
value       Segment mean monthly spend divided by the highest segment's mean monthly spend.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, features as feat

BENEFITS = {
    "dining_credit": {
        "label": "Monthly dining credit",
        "engagement_col": "dining_active_month_share",
        "category_spend_col": "monthly_dining_spend",
    },
    "travel_credit": {
        "label": "Annual travel credit",
        "engagement_col": "travel_active_year_share",
        "category_spend_col": "monthly_travel_spend",
    },
}
HEADROOM_BENCHMARK_QUANTILE = 0.90

WEAKNESSES = [
    "Multiplying three terms weights them equally. Nothing in the data says they should be equal.",
    "Headroom treats a low category share as room to grow. It could equally mean no interest in the category.",
    "Engagement and headroom pull in opposite directions, so the score favors the middle and gives the heaviest "
    "category users a low score. It ranks segments for growth. It says nothing about retention value.",
    "Value is total card spend, not profit. It ignores credit cost, redemption rate, interchange and credit risk.",
    "It is a segment average. Customers inside a segment vary, and a customer-level response model would beat it.",
    "It is built from observed spend, not from observed response to an offer. Only a randomized test can tell "
    "whether the ranking predicts incremental spend.",
    "The 90th percentile benchmark is a choice. A different benchmark shifts headroom for every segment.",
]


def headroom(share: pd.Series | np.ndarray, benchmark: float) -> np.ndarray:
    """1 at zero share of wallet, 0 at or above the benchmark share."""
    return np.clip(1 - np.asarray(share, dtype=float) / benchmark, 0, 1)


def targeting_score(engagement: float, headroom_value: float, value: float) -> float:
    return float(engagement * headroom_value * value)


def score_segments(customers: pd.DataFrame) -> pd.DataFrame:
    """customers needs segment_name, monthly_spend and the columns named in BENEFITS."""
    top_value = customers.groupby("segment_name")["monthly_spend"].mean().max()
    rows = []
    for key, spec in BENEFITS.items():
        share = customers[spec["category_spend_col"]] / customers["monthly_spend"]
        benchmark = float(share.quantile(HEADROOM_BENCHMARK_QUANTILE))
        work = customers.assign(_share=share, _headroom=headroom(share, benchmark))
        for name, sub in work.groupby("segment_name"):
            engagement = sub[spec["engagement_col"]].mean()
            head = sub["_headroom"].mean()
            value = sub["monthly_spend"].mean() / top_value
            rows.append({
                "benefit": key,
                "benefit_label": spec["label"],
                "segment_name": name,
                "n_customers": len(sub),
                "engagement": engagement,
                "headroom": head,
                "value": value,
                "score": targeting_score(engagement, head, value),
                "category_share_of_wallet": sub["_share"].mean(),
                "category_monthly_spend": sub[spec["category_spend_col"]].mean(),
                "headroom_benchmark_share": benchmark,
            })
    out = pd.DataFrame(rows)
    out["rank"] = out.groupby("benefit")["score"].rank(ascending=False, method="first").astype(int)
    out["score_index"] = out["score"] / out.groupby("benefit")["score"].transform("max") * 100
    return out.sort_values(["benefit", "rank"]).reset_index(drop=True)


def run() -> pd.DataFrame:
    customers = feat.load_features().merge(
        pd.read_csv(config.OUTPUT_DIR / "segment_assignments.csv")[["customer_id", "segment_name"]],
        on="customer_id",
    )
    scores = score_segments(customers)
    scores.to_csv(config.OUTPUT_DIR / "targeting_scores.csv", index=False, float_format="%.6f")
    for key in BENEFITS:
        top = scores[(scores.benefit == key) & (scores["rank"] == 1)].iloc[0]
        print(f"Top segment for {top.benefit_label}: {top.segment_name} (score {top.score:.2f})")
    return scores


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(run().round(3).to_string())
