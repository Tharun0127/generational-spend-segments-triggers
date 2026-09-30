"""Feature logic, tested by running the real SQL files on small hand-built data."""
import pytest

from conftest import filler, monthly, tx

ALL_CATEGORIES = {
    "travel": "travel",
    "food_dining": "dining_entertainment",
    "entertainment": "dining_entertainment",
    "grocery_pos": "grocery",
    "grocery_net": "grocery",
    "gas_transport": "gas_transport",
    "shopping_pos": "shopping",
    "shopping_net": "shopping",
    "health_fitness": "health_personal",
    "personal_care": "health_personal",
    "home": "home_kids_pets",
    "kids_pets": "home_kids_pets",
    "misc_pos": "misc",
    "misc_net": "misc",
}


def features(con, customer_id):
    row = con.execute("SELECT * FROM customer_features WHERE customer_id = ?", [customer_id]).df()
    assert len(row) == 1
    return row.iloc[0]


@pytest.mark.parametrize(
    "dob, expected",
    [
        ("1945-12-31", "Silent"),
        ("1946-01-01", "Boomers"),
        ("1964-12-31", "Boomers"),
        ("1965-01-01", "Gen X"),
        ("1980-12-31", "Gen X"),
        ("1981-01-01", "Millennials"),
        ("1996-12-31", "Millennials"),
        ("1997-01-01", "Gen Z"),
    ],
)
def test_generation_uses_pew_cutoffs(build, dob, expected):
    con = build([tx(1, "2019-01-15 12:00", "grocery_pos", 10, dob=dob)])
    assert features(con, 1)["generation"] == expected


def test_fraud_rows_are_excluded(build):
    rows = [
        tx(1, "2019-01-10 12:00", "grocery_pos", 100),
        tx(1, "2019-01-11 12:00", "travel", 5000, fraud=1),
        tx(2, "2019-01-12 12:00", "travel", 900, fraud=1),  # a card with only fraud
    ]
    con = build(rows)
    assert con.execute("SELECT count(*) FROM transactions").fetchone()[0] == 1
    assert features(con, 1)["total_spend"] == 100
    assert features(con, 1)["share_travel"] == 0
    assert con.execute("SELECT count(*) FROM customer_features WHERE customer_id = 2").fetchone()[0] == 0


def test_every_raw_category_maps_to_a_group(build):
    rows = [tx(1, "2019-01-15 12:00", cat, 10) for cat in ALL_CATEGORIES]
    con = build(rows)
    mapping = dict(con.execute("SELECT DISTINCT category, category_group FROM transactions").fetchall())
    assert mapping == ALL_CATEGORIES


def test_share_of_wallet_sums_to_one_and_matches_spend(build):
    rows = [
        tx(1, "2019-01-05 12:00", "travel", 50),
        tx(1, "2019-01-06 12:00", "food_dining", 20),
        tx(1, "2019-01-07 12:00", "entertainment", 10),
        tx(1, "2019-01-08 12:00", "grocery_pos", 120),
    ]
    f = features(build(rows), 1)
    assert f["share_travel"] == pytest.approx(0.25)
    assert f["share_dining_entertainment"] == pytest.approx(0.15)
    assert f["share_grocery"] == pytest.approx(0.60)
    share_cols = [c for c in f.index if c.startswith("share_")]
    assert len(share_cols) == 8
    assert sum(f[c] for c in share_cols) == pytest.approx(1.0)


def test_online_share_uses_only_channel_tagged_spend(build):
    rows = [
        tx(1, "2019-01-05 12:00", "grocery_net", 30),
        tx(1, "2019-01-06 12:00", "shopping_pos", 70),
        tx(1, "2019-01-07 12:00", "travel", 1000),  # untagged, must not dilute the share
    ]
    assert features(build(rows), 1)["online_share"] == pytest.approx(0.30)


def test_online_share_is_zero_when_nothing_is_tagged(build):
    assert features(build([tx(1, "2019-01-05 12:00", "travel", 10)]), 1)["online_share"] == 0


def test_weekend_and_late_night_shares(build):
    rows = [
        tx(1, "2019-01-05 12:00", "home", 10),  # Saturday, midday
        tx(1, "2019-01-06 23:30", "home", 10),  # Sunday, late night
        tx(1, "2019-01-07 04:59", "home", 10),  # Monday, late night (before 05:00)
        tx(1, "2019-01-08 05:00", "home", 10),  # Tuesday, not late night
        tx(1, "2019-01-09 21:59", "home", 10),  # Wednesday, not late night
    ]
    f = features(build(rows), 1)
    assert f["weekend_share"] == pytest.approx(2 / 5)
    assert f["late_night_share"] == pytest.approx(2 / 5)


def test_rfm_and_average_ticket(build):
    rows = [
        tx(1, "2019-01-10 12:00", "home", 100),
        tx(1, "2019-03-10 12:00", "home", 200),
        tx(1, "2019-03-20 12:00", "home", 300),
        tx(2, "2019-03-31 12:00", "home", 50),  # sets the last date in the data
    ]
    f = features(build(rows), 1)
    assert f["active_months"] == 3                     # Jan to Mar inclusive, Feb counts as active tenure
    assert f["monthly_txns"] == pytest.approx(1.0)     # 3 transactions over 3 months
    assert f["monthly_spend"] == pytest.approx(200.0)  # 600 over 3 months
    assert f["avg_ticket"] == pytest.approx(200.0)
    assert f["recency_days"] == 11                     # Mar 20 to Mar 31


def test_customer_month_fills_gap_months_with_zero(build):
    rows = [tx(1, "2019-01-10 12:00", "home", 100), tx(1, "2019-03-10 12:00", "home", 100),
            tx(2, "2019-02-10 12:00", "home", 5)]  # another customer makes February exist
    con = build(rows)
    months = con.execute(
        "SELECT month_idx, spend FROM customer_month WHERE customer_id = 1 ORDER BY month"
    ).fetchall()
    assert months == [(1, 100.0), (2, 0.0), (3, 100.0)]


def test_volatility_is_cv_of_monthly_spend(build):
    steady = monthly(1, "home", [100, 100, 100, 100])
    swingy = monthly(2, "home", [50, 150, 50, 150])
    con = build(steady + swingy)
    assert features(con, 1)["spend_volatility"] == pytest.approx(0.0)
    # sample std of [50,150,50,150] is 57.735, mean is 100
    assert features(con, 2)["spend_volatility"] == pytest.approx(0.57735, abs=1e-4)


def test_quarter_over_quarter_change_uses_lag(build):
    # Q1 = 300, Q2 = 450, Q3 = 225
    rows = monthly(1, "home", [100, 100, 100, 150, 150, 150, 75, 75, 75])
    con = build(rows)
    q = con.execute(
        "SELECT spend, prev_q_spend, qoq_spend_change FROM customer_quarter WHERE customer_id = 1 ORDER BY quarter"
    ).fetchall()
    assert q[0] == (300.0, None, None)
    assert q[1] == (450.0, 300.0, pytest.approx(0.5))
    assert q[2] == (225.0, 450.0, pytest.approx(-0.5))
    assert features(con, 1)["last_qoq_spend_change"] == pytest.approx(-0.5)
    assert features(con, 1)["avg_qoq_spend_change"] == pytest.approx(0.0)


def test_year_over_year_change_uses_lag_four(build):
    rows = monthly(1, "home", [100] * 12 + [120] * 12)
    con = build(rows)
    yoy = con.execute(
        "SELECT yoy_spend_change FROM customer_quarter WHERE customer_id = 1 ORDER BY quarter"
    ).df()["yoy_spend_change"]
    assert yoy.iloc[:4].isna().all()
    assert yoy.iloc[4:].tolist() == pytest.approx([0.2] * 4)


def test_benefit_inputs(build):
    rows = (
        filler(1, 24)
        + monthly(1, "food_dining", [40] * 12 + [0] * 12)          # dining in half the months
        + [tx(1, "2019-05-05 12:00", "travel", 450), tx(1, "2020-05-05 12:00", "travel", 20)]
    )
    f = features(build(rows), 1)
    assert f["dining_active_month_share"] == pytest.approx(0.5)
    assert f["travel_active_year_share"] == pytest.approx(0.5)      # only 2019 has a $100+ travel purchase
    assert f["monthly_dining_spend"] == pytest.approx(20.0)
