"""Load the raw CSVs into DuckDB and build the customer feature tables with SQL."""
from __future__ import annotations

import pandas as pd

from . import config, db


def load_raw(con) -> None:
    raw_glob = (config.RAW_DIR / "fraud*.csv").as_posix()
    db.set_variables(con, {"raw_glob": raw_glob})
    db.run_sql_file(con, "01_load_raw.sql")


def check_features(features: pd.DataFrame) -> None:
    """Cheap sanity checks that would catch a broken join or mapping."""
    assert features["customer_id"].is_unique, "duplicate customers in feature table"
    shares = features[config.SHARE_COLS].sum(axis=1)
    assert (shares - 1).abs().max() < 1e-9, "share of wallet does not sum to 1"
    assert features[config.CLUSTER_FEATURES].notna().all().all(), "nulls in cluster features"
    assert features["generation"].isin(config.GENERATIONS).all(), "unknown generation label"


def build() -> pd.DataFrame:
    con = db.connect()
    load_raw(con)
    db.build_features(con)
    unmapped = con.execute(
        "SELECT count(*) FROM transactions WHERE category_group = 'unmapped'"
    ).fetchone()[0]
    assert unmapped == 0, f"{unmapped} transactions have an unmapped category"
    features = con.execute("SELECT * FROM customer_features ORDER BY customer_id").df()
    con.close()

    check_features(features)
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    features.to_parquet(config.OUTPUT_DIR / "customer_features.parquet", index=False)
    print(f"Built features for {len(features):,} customers, {features.shape[1]} columns.")
    return features


def load_features() -> pd.DataFrame:
    return pd.read_parquet(config.OUTPUT_DIR / "customer_features.parquet")


if __name__ == "__main__":
    build()
