"""Behavioral segmentation: K-means with k selection, stability and a generator check."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.mixture import GaussianMixture
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler

from . import config, features as feat, stats


def prepare_matrix(features: pd.DataFrame) -> np.ndarray:
    """log1p to tame right skew, then standard scaling so no feature dominates on units."""
    logged = np.log1p(features[config.CLUSTER_FEATURES].to_numpy(dtype=float))
    return StandardScaler().fit_transform(logged)


def fit_kmeans(x: np.ndarray, k: int, seed: int = config.SEED) -> KMeans:
    return KMeans(n_clusters=k, n_init=10, random_state=seed).fit(x)


def bootstrap_ari(x: np.ndarray, k: int, reference: np.ndarray, n_boot: int = config.N_BOOTSTRAP) -> np.ndarray:
    """Refit on resampled customers, label everyone, compare with the full-data labels.

    ARI is 1 when two labelings agree perfectly and about 0 when agreement is at chance.
    """
    rng = np.random.default_rng(config.SEED)
    scores = []
    for b in range(n_boot):
        idx = rng.integers(0, len(x), len(x))
        model = KMeans(n_clusters=k, n_init=5, random_state=b).fit(x[idx])
        scores.append(adjusted_rand_score(reference, model.predict(x)))
    return np.array(scores)


def select_k(x: np.ndarray) -> tuple[pd.DataFrame, dict[int, np.ndarray]]:
    rows, labels_by_k = [], {}
    for k in config.K_RANGE:
        km = fit_kmeans(x, k)
        labels_by_k[k] = km.labels_
        ari = bootstrap_ari(x, k, km.labels_)
        gmm = GaussianMixture(
            n_components=k, covariance_type="full", reg_covar=1e-3, n_init=3, random_state=config.SEED
        ).fit(x)
        rows.append({
            "k": k,
            "inertia": km.inertia_,
            "silhouette": silhouette_score(x, km.labels_),
            "bootstrap_ari_mean": ari.mean(),
            "bootstrap_ari_p05": np.percentile(ari, 5),
            "smallest_segment": int(np.bincount(km.labels_).min()),
            "gmm_bic": gmm.bic(x),
            "gmm_vs_kmeans_ari": adjusted_rand_score(km.labels_, gmm.predict(x)),
        })
    table = pd.DataFrame(rows)
    # Elbow helper: how much inertia each extra cluster removes, as a share of the previous value.
    table["inertia_drop_pct"] = -table["inertia"].pct_change()
    return table, labels_by_k


def order_by_spend(features: pd.DataFrame, labels: np.ndarray) -> np.ndarray:
    """Renumber clusters 1..k from highest to lowest mean monthly spend, so ids are stable."""
    means = features.groupby(labels)["monthly_spend"].mean().sort_values(ascending=False)
    mapping = {old: new for new, old in enumerate(means.index, start=1)}
    return np.array([mapping[label] for label in labels])


def name_segment(row: pd.Series, portfolio: pd.Series) -> str:
    """Rule-based business name from the profile, so names survive a rebuild."""
    spend_index = row["monthly_spend"] / portfolio["monthly_spend"]
    if row["share_travel"] / portfolio["share_travel"] >= 2:
        return "Big-Ticket Travelers"
    if row["online_share"] / portfolio["online_share"] >= 1.15:
        return "Digital Shoppers"
    if spend_index >= 1.3:
        return "Premium Household Shoppers"
    if spend_index <= 0.75:
        return "Light Home and Dining Spenders"
    return "Mainstream Everyday Spenders"


def profile_segments(features: pd.DataFrame) -> pd.DataFrame:
    portfolio = features[config.CLUSTER_FEATURES + ["median_ticket"]].mean()
    total_spend = features["total_spend"].sum()
    rows = []
    for seg, sub in features.groupby("segment_id"):
        shares = sub[config.SHARE_COLS].mean()
        index = (shares / portfolio[config.SHARE_COLS]).sort_values(ascending=False)
        row = {
            "segment_id": seg,
            "n_customers": len(sub),
            "customer_share": len(sub) / len(features),
            "spend_share": sub["total_spend"].sum() / total_spend,
            "monthly_spend": sub["monthly_spend"].mean(),
            "monthly_txns": sub["monthly_txns"].mean(),
            "avg_ticket": sub["avg_ticket"].mean(),
            "median_ticket": sub["median_ticket"].mean(),
            "online_share": sub["online_share"].mean(),
            "weekend_share": sub["weekend_share"].mean(),
            "late_night_share": sub["late_night_share"].mean(),
            "spend_volatility": sub["spend_volatility"].mean(),
            "median_age": sub["age_at_end"].median(),
            "pct_female": (sub["gender"] == "F").mean(),
            **shares.to_dict(),
            "top_categories": " | ".join(
                config.CATEGORY_GROUPS[c.replace("share_", "")] for c in shares.sort_values(ascending=False).index[:3]
            ),
            "over_indexed": " | ".join(
                f"{config.CATEGORY_GROUPS[c.replace('share_', '')]} ({v:.1f}x)" for c, v in index.head(2).items()
            ),
        }
        gen_mix = sub["generation"].value_counts(normalize=True)
        for gen in config.GENERATIONS:
            row[f"gen_{gen}"] = float(gen_mix.get(gen, 0.0))
        rows.append(row)
    profiles = pd.DataFrame(rows)
    profiles.insert(1, "segment_name", [name_segment(r, portfolio) for _, r in profiles.iterrows()])
    assert profiles["segment_name"].is_unique, "two segments got the same name, revisit name_segment"
    return profiles


def generator_check(features: pd.DataFrame, buckets: pd.DataFrame) -> dict:
    """How much of the segmentation is explained by the generator's own buckets?"""
    df = features.merge(buckets, on="customer_id")
    seg = df["segment_id"]
    associations = {}
    for label, col in {
        "generation": "generation",
        "inferred_age_band": "age_band",
        "gender": "gender",
        "city_size_band": "city_size_band",
        "transactions_per_day_tier": "txns_per_day_tier",
    }.items():
        associations[label] = stats.cramers_v(pd.crosstab(seg, df[col]))["effect_size"]

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=config.SEED)
    forest = RandomForestClassifier(n_estimators=300, min_samples_leaf=5, random_state=config.SEED)
    demo = pd.DataFrame({
        "birth_year": df["birth_year"],
        "is_female": (df["gender"] == "F").astype(int),
        "log_city_pop": np.log10(df["city_pop"]),
    })
    demo_acc = cross_val_score(forest, demo, seg, cv=cv).mean()
    with_tier = demo.assign(txns_per_day_tier=df["txns_per_day_tier"])
    tier_acc = cross_val_score(forest, with_tier, seg, cv=cv).mean()
    baseline = seg.value_counts(normalize=True).max()
    return {
        "cramers_v": associations,
        "majority_baseline_accuracy": float(baseline),
        "demographics_only_accuracy": float(demo_acc),
        "demographics_plus_frequency_tier_accuracy": float(tier_acc),
        "note": (
            "Accuracy is 5-fold cross-validated random forest accuracy at predicting the segment "
            "from birth year, gender and city population only, then with the transactions-per-day tier added."
        ),
    }


def run() -> dict:
    features = feat.load_features()
    buckets = pd.read_csv(config.OUTPUT_DIR / "customer_generator_buckets.csv")
    x = prepare_matrix(features)

    k_table, labels_by_k = select_k(x)
    k = config.CHOSEN_K
    features["segment_id"] = order_by_spend(features, labels_by_k[k])
    profiles = profile_segments(features)
    names = profiles.set_index("segment_id")["segment_name"]
    features["segment_name"] = features["segment_id"].map(names)

    coords = PCA(n_components=2, random_state=config.SEED).fit(x)
    xy = coords.transform(x)
    assignments = features[["customer_id", "segment_id", "segment_name", "generation"]].assign(
        pca_1=xy[:, 0], pca_2=xy[:, 1]
    )
    check = generator_check(features, buckets)
    check["pca_variance_explained"] = coords.explained_variance_ratio_.round(4).tolist()
    check["chosen_k"] = k

    k_table.to_csv(config.OUTPUT_DIR / "k_selection.csv", index=False)
    profiles.to_csv(config.OUTPUT_DIR / "segment_profiles.csv", index=False)
    assignments.to_csv(config.OUTPUT_DIR / "segment_assignments.csv", index=False)
    (config.OUTPUT_DIR / "generator_check.json").write_text(json.dumps(check, indent=2), encoding="utf-8")
    print(f"Segmentation done with k = {k}: " + ", ".join(f"{n} ({c})" for n, c in zip(profiles.segment_name, profiles.n_customers)))
    return {"k_table": k_table, "profiles": profiles, "assignments": assignments, "check": check}


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 60)
    out = run()
    print(out["k_table"].round(3).to_string())
    print(out["profiles"].round(3).T.to_string())
    print(json.dumps(out["check"], indent=2))
