"""Effect sizes, the targeting score and the segmentation helpers."""
import numpy as np
import pandas as pd
import pytest

from conftest import tx  # noqa: F401  (imports conftest so src is on the path)
from src import segmentation, stats, targeting, triggers


def test_epsilon_squared_is_near_one_for_fully_separated_groups():
    values = pd.Series(list(range(30)))
    groups = pd.Series(["a"] * 10 + ["b"] * 10 + ["c"] * 10)
    res = stats.kruskal_with_effect(values, groups)
    assert res["effect_size"] > 0.85
    assert res["p_value"] < 0.001


def test_epsilon_squared_is_near_zero_for_identical_groups():
    rng = np.random.default_rng(0)
    values = pd.Series(rng.normal(size=600))
    groups = pd.Series(np.tile(["a", "b", "c"], 200))
    assert stats.kruskal_with_effect(values, groups)["effect_size"] < 0.02


def test_cramers_v_bounds():
    perfect = pd.DataFrame([[50, 0], [0, 50]])
    independent = pd.DataFrame([[25, 25], [25, 25]])
    assert stats.cramers_v(perfect)["effect_size"] == pytest.approx(1.0, abs=0.02)
    assert stats.cramers_v(independent)["effect_size"] == pytest.approx(0.0, abs=1e-9)


def test_holm_adjustment_matches_hand_calculation():
    # sorted p: 0.01, 0.02, 0.04 -> 0.03, 0.04, 0.04
    assert stats.holm_adjust([0.04, 0.01, 0.02]) == pytest.approx([0.04, 0.03, 0.04])
    assert max(stats.holm_adjust([0.5, 0.9])) <= 1.0


def test_effect_labels():
    assert [stats.effect_label(e) for e in (0.005, 0.03, 0.10, 0.30)] == ["negligible", "small", "medium", "large"]


def test_headroom_is_clipped_between_zero_and_one():
    out = targeting.headroom(np.array([0.0, 0.05, 0.10, 0.25]), benchmark=0.10)
    assert out.tolist() == pytest.approx([1.0, 0.5, 0.0, 0.0])


def test_targeting_score_is_the_product_of_its_parts():
    assert targeting.targeting_score(0.8, 0.5, 0.25) == pytest.approx(0.1)
    assert targeting.targeting_score(0.8, 0.0, 1.0) == 0


def test_score_segments_ranks_engaged_high_value_segments_with_room_first():
    def segment(name, n, spend, dining, active):
        return pd.DataFrame({
            "segment_name": name,
            "monthly_spend": spend,
            "monthly_dining_spend": dining,
            "dining_active_month_share": active,
            "monthly_travel_spend": 10.0,
            "travel_active_year_share": 0.5,
        }, index=range(n))

    customers = pd.concat([
        segment("High value, room to grow", 10, 10_000, 200, 1.0),
        segment("Low value, room to grow", 10, 2_000, 40, 1.0),
        segment("Saturated", 10, 10_000, 3_000, 1.0),
    ], ignore_index=True)
    scores = targeting.score_segments(customers)
    dining = scores[scores.benefit == "dining_credit"].set_index("segment_name")
    assert dining.loc["High value, room to grow", "rank"] == 1
    assert dining.loc["Saturated", "score"] == 0            # at or above the benchmark share
    assert dining.loc["High value, room to grow", "value"] == 1.0
    assert dining.loc["Low value, room to grow", "value"] == pytest.approx(0.2)
    assert dining["score_index"].max() == 100


def test_segments_are_numbered_from_highest_to_lowest_spend():
    features = pd.DataFrame({"monthly_spend": [10, 12, 500, 520, 90, 100]})
    labels = np.array([2, 2, 0, 0, 1, 1])
    assert segmentation.order_by_spend(features, labels).tolist() == [3, 3, 1, 1, 2, 2]


def test_trigger_overlap_counts_same_month_and_ever():
    events = pd.DataFrame({
        "customer_id": [1, 1, 2, 3],
        "month": pd.to_datetime(["2019-06-01", "2019-06-01", "2019-07-01", "2019-08-01"]),
        "trigger_name": ["travel_drop", "dining_cooling", "travel_drop", "dining_cooling"],
        "spend_at_stake": [1.0, 1.0, 1.0, 1.0],
    })
    out = triggers.overlap(events).set_index(["trigger_a", "trigger_b"])
    row = out.loc[("travel_drop", "dining_cooling")]
    assert row["same_month_both"] == 1
    assert row["customers_ever_both"] == 1
    assert row["customers_ever_either"] == 3


def test_deseasonalise_removes_a_shared_monthly_pattern():
    cm = pd.DataFrame({
        "customer_id": [1, 1, 2, 2],
        "month": pd.to_datetime(["2019-01-01", "2019-02-01"] * 2),
        "travel_spend": [100.0, 200.0, 300.0, 600.0],   # everyone doubles in February
        "dining_spend": [10.0, 10.0, 10.0, 10.0],
        "dining_txns": [1.0, 1.0, 1.0, 1.0],
    })
    flat = triggers.deseasonalise(cm)
    per_customer = flat.groupby("customer_id")["travel_spend"].agg(["min", "max"])
    assert (per_customer["max"] - per_customer["min"]).abs().max() < 1e-9
