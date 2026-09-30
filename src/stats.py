"""Small statistics helpers: tests with effect sizes, not only p-values."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def epsilon_squared(h: float, n: int) -> float:
    """Effect size for Kruskal-Wallis. 0 = no separation between groups, 1 = complete."""
    return float(h / (n - 1)) if n > 1 else float("nan")


def kruskal_with_effect(values: pd.Series, groups: pd.Series) -> dict:
    samples = [v.to_numpy() for _, v in values.groupby(groups, observed=True) if len(v) > 0]
    if len(samples) < 2:
        return {"statistic": np.nan, "p_value": np.nan, "effect_size": np.nan, "n": len(values)}
    h, p = stats.kruskal(*samples)
    return {
        "statistic": float(h),
        "p_value": float(p),
        "effect_size": epsilon_squared(h, len(values)),
        "n": int(len(values)),
    }


def cramers_v(table: pd.DataFrame) -> dict:
    """Chi-square test of independence with bias-corrected Cramer's V."""
    table = table.loc[table.sum(axis=1) > 0, table.sum(axis=0) > 0]
    chi2, p, _, _ = stats.chi2_contingency(table.to_numpy(), correction=False)
    n = table.to_numpy().sum()
    r, c = table.shape
    phi2 = max(0.0, chi2 / n - (r - 1) * (c - 1) / (n - 1))
    r_adj = r - (r - 1) ** 2 / (n - 1)
    c_adj = c - (c - 1) ** 2 / (n - 1)
    denom = min(r_adj - 1, c_adj - 1)
    v = float(np.sqrt(phi2 / denom)) if denom > 0 else float("nan")
    return {"statistic": float(chi2), "p_value": float(p), "effect_size": v, "n": int(n)}


def holm_adjust(p_values: list[float]) -> list[float]:
    """Holm step-down adjustment for multiple comparisons."""
    p = np.asarray(p_values, dtype=float)
    order = np.argsort(p)
    adjusted = np.empty_like(p)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (len(p) - rank) * p[idx])
        adjusted[idx] = min(1.0, running)
    return adjusted.tolist()


def effect_label(effect: float) -> str:
    """Conventional bands for eta or epsilon squared."""
    if np.isnan(effect):
        return "n/a"
    if effect < 0.01:
        return "negligible"
    if effect < 0.06:
        return "small"
    if effect < 0.14:
        return "medium"
    return "large"


def median_ci(values: np.ndarray, n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% bootstrap interval for the median."""
    rng = np.random.default_rng(seed)
    values = np.asarray(values, dtype=float)
    idx = rng.integers(0, len(values), size=(n_boot, len(values)))
    medians = np.median(values[idx], axis=1)
    lo, hi = np.percentile(medians, [2.5, 97.5])
    return float(lo), float(hi)
