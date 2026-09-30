"""Compare generations on behavior, with effect sizes and a generator-artifact check."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeRegressor

from . import config, features as feat, stats

METRICS = [
    *config.SHARE_COLS,
    "online_share",
    "avg_ticket",
    "median_ticket",
    "monthly_txns",
    "monthly_spend",
    "weekend_share",
    "late_night_share",
]
AGE_BANDS = ["Older band", "Middle band", "Younger band"]


def infer_age_bands(features: pd.DataFrame) -> tuple[pd.Series, list[int]]:
    """Find the two birth-year cut points where behavior steps.

    The generator assigns behavior by age band, not by generation. A three-leaf
    regression tree on birth year recovers where those bands start and end. We fit
    it on late-night share because that feature steps cleanly in the raw data.
    """
    x = features[["birth_year"]].to_numpy()
    tree = DecisionTreeRegressor(max_leaf_nodes=3, random_state=config.SEED)
    tree.fit(x, features["late_night_share"])
    cuts = sorted(int(np.floor(t)) for t in tree.tree_.threshold if t > 0)
    band = pd.cut(
        features["birth_year"],
        bins=[-np.inf, cuts[0], cuts[1], np.inf],
        labels=AGE_BANDS,
    )
    return band.astype(str), cuts


def summarise(features: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for gen in config.GENERATIONS:
        sub = features[features["generation"] == gen]
        for metric in METRICS:
            lo, hi = stats.median_ci(sub[metric].to_numpy(), seed=config.SEED)
            rows.append({
                "generation": gen,
                "n_customers": len(sub),
                "metric": metric,
                "median": sub[metric].median(),
                "mean": sub[metric].mean(),
                "median_ci_low": lo,
                "median_ci_high": hi,
            })
    return pd.DataFrame(rows)


def run_tests(features: pd.DataFrame, band: pd.Series) -> pd.DataFrame:
    rows = []
    for metric in METRICS:
        by_gen = stats.kruskal_with_effect(features[metric], features["generation"])
        by_band = stats.kruskal_with_effect(features[metric], band)
        # Does generation still matter once we hold the generator's age band fixed?
        within = []
        for b in AGE_BANDS:
            mask = band == b
            counts = features.loc[mask, "generation"].value_counts()
            keep = counts[counts >= 20].index  # skip slivers such as 3 Millennials
            sub = features[mask & features["generation"].isin(keep)]
            if sub["generation"].nunique() >= 2:
                res = stats.kruskal_with_effect(sub[metric], sub["generation"])
                within.append((len(sub), res["effect_size"]))
        within_effect = (
            float(np.average([e for _, e in within], weights=[n for n, _ in within]))
            if within else np.nan
        )
        rows.append({
            "metric": metric,
            "test": "Kruskal-Wallis",
            "statistic": by_gen["statistic"],
            "p_value": by_gen["p_value"],
            "effect_size": by_gen["effect_size"],
            "effect_measure": "epsilon squared",
            "effect_by_age_band": by_band["effect_size"],
            "effect_within_age_band": within_effect,
        })

    # Chi-square: is the customer's biggest category independent of generation?
    top_cat = features[config.SHARE_COLS].idxmax(axis=1).str.replace("share_", "")
    for name, series in {"top_category_group": top_cat, "txns_per_day_tier": features["txns_per_day_tier"]}.items():
        res = stats.cramers_v(pd.crosstab(features["generation"], series))
        band_res = stats.cramers_v(pd.crosstab(band, series))
        rows.append({
            "metric": name,
            "test": "Chi-square",
            "statistic": res["statistic"],
            "p_value": res["p_value"],
            "effect_size": res["effect_size"],
            "effect_measure": "Cramer's V",
            "effect_by_age_band": band_res["effect_size"],
            "effect_within_age_band": np.nan,
        })

    out = pd.DataFrame(rows)
    out["p_holm"] = stats.holm_adjust(out["p_value"].tolist())
    out["effect_label"] = [
        stats.effect_label(e) if m == "epsilon squared" else "" for e, m in zip(out["effect_size"], out["effect_measure"])
    ]
    return out.sort_values("effect_size", ascending=False).reset_index(drop=True)


def build_insights(summary: pd.DataFrame, tests: pd.DataFrame, cuts: list[int]) -> list[dict]:
    """Five insights for a card product team. Every number is read from the tables."""
    med = summary.pivot(index="generation", columns="metric", values="median")
    eff = tests.set_index("metric")["effect_size"]
    p_val = tests.set_index("metric")["p_value"]
    ci = summary[summary["metric"] == "median_ticket"].set_index("generation")
    n_gen_z = int(ci.loc["Gen Z", "n_customers"])

    def pct(gen: str, metric: str) -> str:
        return f"{med.loc[gen, metric] * 100:.0f}%"

    return [
        {
            "title": "Gen Z shops, older generations buy groceries",
            "metric": "share_shopping",
            "text": (
                f"Gen Z puts {pct('Gen Z', 'share_shopping')} of spend into shopping and "
                f"{pct('Gen Z', 'share_grocery')} into grocery, while Boomers put "
                f"{pct('Boomers', 'share_shopping')} into shopping and {pct('Boomers', 'share_grocery')} "
                f"into grocery (epsilon squared {eff['share_shopping']:.2f} and {eff['share_grocery']:.2f})."
            ),
        },
        {
            "title": "Gen Z is the most online generation",
            "metric": "online_share",
            "text": (
                f"Gen Z makes {pct('Gen Z', 'online_share')} of its channel-tagged spend online "
                f"against {pct('Millennials', 'online_share')} for Millennials and "
                f"{pct('Boomers', 'online_share')} for Boomers (epsilon squared {eff['online_share']:.2f})."
            ),
        },
        {
            "title": "Customers from Gen X down transact about half again as often as Boomers",
            "metric": "monthly_txns",
            "text": (
                f"Gen X and Millennials make {med.loc['Millennials', 'monthly_txns']:.0f} transactions a month and "
                f"Gen Z {med.loc['Gen Z', 'monthly_txns']:.0f}, against {med.loc['Boomers', 'monthly_txns']:.0f} for "
                f"Boomers and Silent (epsilon squared {eff['monthly_txns']:.2f}); Gen Z's lower median ticket "
                f"(${med.loc['Gen Z', 'median_ticket']:.0f} against ${med.loc['Boomers', 'median_ticket']:.0f}) is not "
                f"reliable with {n_gen_z} customers (95% interval ${ci.loc['Gen Z', 'median_ci_low']:.0f} to "
                f"${ci.loc['Gen Z', 'median_ci_high']:.0f})."
            ),
        },
        {
            "title": "Gen X and Millennials carry the most spend per customer",
            "metric": "monthly_spend",
            "text": (
                f"Median monthly spend is ${med.loc['Millennials', 'monthly_spend']:,.0f} for Millennials and "
                f"${med.loc['Gen X', 'monthly_spend']:,.0f} for Gen X, against "
                f"${med.loc['Boomers', 'monthly_spend']:,.0f} for Boomers and "
                f"${med.loc['Silent', 'monthly_spend']:,.0f} for Silent (epsilon squared {eff['monthly_spend']:.2f})."
            ),
        },
        {
            "title": "Travel share of wallet does not depend on generation",
            "metric": "share_travel",
            "text": (
                f"Median travel share of wallet runs from {med.loc['Gen Z', 'share_travel'] * 100:.1f}% for Gen Z to "
                f"{med.loc['Silent', 'share_travel'] * 100:.1f}% for Silent and the difference is not reliable "
                f"(epsilon squared {eff['share_travel']:.3f}, p = {p_val['share_travel']:.2f}), so a travel "
                f"benefit should be targeted on behavior, not on age."
            ),
        },
    ]


def run() -> dict:
    features = feat.load_features()
    features["txns_per_day_tier"] = (features["n_txns"] / (features["active_months"] * 30.44)).round().astype(int)
    band, cuts = infer_age_bands(features)

    summary = summarise(features)
    tests = run_tests(features, band)
    insights = build_insights(summary, tests, cuts)

    band_mix = pd.crosstab(features["generation"], band).reindex(config.GENERATIONS)[AGE_BANDS]
    kw = tests[tests["test"] == "Kruskal-Wallis"]
    artifact = {
        "birth_year_cuts": cuts,
        "band_definition": {
            "Older band": f"born {cuts[0]} or earlier",
            "Middle band": f"born {cuts[0] + 1} to {cuts[1]}",
            "Younger band": f"born {cuts[1] + 1} or later",
        },
        "generation_by_band": band_mix.to_dict(orient="index"),
        "median_effect_by_generation": float(kw["effect_size"].median()),
        "median_effect_by_age_band": float(kw["effect_by_age_band"].median()),
        "median_effect_within_age_band": float(kw["effect_within_age_band"].median()),
        "max_effect_within_age_band": float(kw["effect_within_age_band"].max()),
    }

    summary.to_csv(config.OUTPUT_DIR / "generation_summary.csv", index=False, float_format="%.6f")
    tests.to_csv(config.OUTPUT_DIR / "generation_tests.csv", index=False, float_format="%.6f")
    (config.OUTPUT_DIR / "generation_insights.json").write_text(
        json.dumps({"insights": insights, "artifact_check": artifact}, indent=2), encoding="utf-8"
    )
    features.assign(age_band=band)[["customer_id", "age_band", "txns_per_day_tier"]].to_csv(
        config.OUTPUT_DIR / "customer_generator_buckets.csv", index=False
    )
    print(f"Generation tests done. Behavior steps at birth years {cuts}.")
    return {"summary": summary, "tests": tests, "insights": insights, "artifact": artifact}


if __name__ == "__main__":
    result = run()
    pd.set_option("display.width", 220)
    print(result["tests"].round(4).to_string())
    print(json.dumps(result["artifact"], indent=2))
    for item in result["insights"]:
        print("-", item["text"])
