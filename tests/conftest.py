"""Shared helpers: build a tiny raw_transactions table in memory and run the real SQL on it."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import db  # noqa: E402

_counter = iter(range(1, 10_000_000))


def tx(cc, ts, category, amt, fraud=0, dob="1985-06-15", gender="F", city_pop=5000):
    """One raw transaction row."""
    return {
        "trans_num": f"t{next(_counter)}",
        "trans_ts": pd.Timestamp(ts),
        "cc_num": cc,
        "category": category,
        "amt": float(amt),
        "gender": gender,
        "city_pop": city_pop,
        "dob": pd.Timestamp(dob).date(),
        "is_fraud": fraud,
    }


def monthly(cc, category, amounts, start="2019-01", counts=None, **kwargs):
    """One transaction per month (or counts[i] transactions) on the 15th, from `start`.

    An amount of 0 or None means no transaction that month. When counts is given, the
    month's amount is split evenly across that many transactions.
    """
    rows = []
    for i, period in enumerate(pd.period_range(start, periods=len(amounts), freq="M")):
        amount = amounts[i]
        n = 1 if counts is None else counts[i]
        if not amount or not n:
            continue
        for j in range(n):
            rows.append(tx(cc, f"{period}-15 12:{j:02d}:00", category, amount / n, **kwargs))
    return rows


def filler(cc, n_months, start="2019-01", **kwargs):
    """A small grocery purchase every month so the customer has a row for every month."""
    return monthly(cc, "grocery_pos", [10] * n_months, start=start, **kwargs)


@pytest.fixture
def build():
    """Return a function that loads rows and runs the feature SQL (and optionally triggers)."""
    connections = []

    def _build(rows, trigger_params=None, triggers=False):
        con = db.connect(":memory:")
        raw_df = pd.DataFrame(rows)  # noqa: F841  (referenced by DuckDB below)
        con.execute("CREATE TABLE raw_transactions AS SELECT * FROM raw_df")
        db.build_features(con)
        if triggers or trigger_params is not None:
            db.build_triggers(con, trigger_params)
        connections.append(con)
        return con

    yield _build
    for con in connections:
        con.close()
