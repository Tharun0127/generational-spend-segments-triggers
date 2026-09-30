"""Trigger logic, tested by running sql/06_triggers.sql on small hand-built data."""
import pandas as pd

from conftest import filler, monthly

NO_ADJUST = {"portfolio_adjust": 0}


def fires(con, trigger, customer_id=1):
    """Months (as 'YYYY-MM') in which the trigger fired for the customer."""
    rows = con.execute(
        "SELECT month FROM trigger_events WHERE trigger_name = ? AND customer_id = ? ORDER BY month",
        [trigger, customer_id],
    ).fetchall()
    return [pd.Timestamp(r[0]).strftime("%Y-%m") for r in rows]


# --- travel drop ---------------------------------------------------------------------------

def test_travel_drop_fires_when_three_month_spend_falls_more_than_half(build):
    # prior 3 months = 900, current 3 months = 300: down 67%
    rows = filler(1, 6) + monthly(1, "travel", [300, 300, 300, 100, 100, 100])
    con = build(rows, NO_ADJUST)
    assert fires(con, "travel_drop") == ["2019-06"]
    stake = con.execute("SELECT spend_at_stake FROM trigger_events WHERE trigger_name = 'travel_drop'").fetchone()[0]
    assert stake == 600


def test_travel_drop_does_not_fire_at_exactly_half(build):
    rows = filler(1, 6) + monthly(1, "travel", [300, 300, 300, 150, 150, 150])
    assert fires(build(rows, NO_ADJUST), "travel_drop") == []


def test_travel_drop_needs_a_minimum_base(build):
    # down 90%, but the prior window is only $150 against a $200 floor
    rows = filler(1, 6) + monthly(1, "travel", [50, 50, 50, 5, 5, 5])
    assert fires(build(rows, NO_ADJUST), "travel_drop") == []
    assert fires(build(rows, {**NO_ADJUST, "travel_min_base": 100.0}), "travel_drop") == ["2019-06"]


def test_travel_drop_does_not_refire_while_the_drop_persists(build):
    # Spend collapses in month 4 and stays low. The rolling windows stay "down" for several
    # months, but the customer should be contacted once.
    rows = filler(1, 9) + monthly(1, "travel", [400, 400, 400, 10, 10, 10, 10, 10, 10])
    assert fires(build(rows, NO_ADJUST), "travel_drop") == ["2019-06"]


def test_travel_drop_can_fire_again_after_recovery_and_cooldown(build):
    travel = [400, 400, 400, 10, 10, 10,      # first drop, fires in month 6
              400, 400, 400, 400, 400, 400,   # recovers
              10, 10, 10]                     # second drop
    rows = filler(1, 15) + monthly(1, "travel", travel)
    assert fires(build(rows, NO_ADJUST), "travel_drop") == ["2019-06", "2020-02"]


def test_portfolio_adjustment_ignores_a_drop_everyone_shares(build):
    # Both customers fall 70%. That is seasonality, not a personal change.
    rows = []
    for cc in (1, 2):
        rows += filler(cc, 6) + monthly(cc, "travel", [1000, 1000, 1000, 300, 300, 300])
    assert fires(build(rows, NO_ADJUST), "travel_drop") == ["2019-06"]
    assert fires(build(rows, {"portfolio_adjust": 1}), "travel_drop") == []


def test_portfolio_adjustment_still_catches_a_customer_who_falls_more(build):
    rows = []
    for cc in range(2, 12):  # ten customers fall 20%
        rows += filler(cc, 6) + monthly(cc, "travel", [1000, 1000, 1000, 800, 800, 800])
    rows += filler(1, 6) + monthly(1, "travel", [1000, 1000, 1000, 100, 100, 100])  # one falls 90%
    con = build(rows, {"portfolio_adjust": 1})
    assert fires(con, "travel_drop", customer_id=1) == ["2019-06"]
    assert fires(con, "travel_drop", customer_id=2) == []


# --- first travel --------------------------------------------------------------------------

def test_first_travel_fires_once_in_the_month_of_the_first_purchase(build):
    rows = filler(1, 8) + monthly(1, "travel", [0, 0, 0, 0, 250, 0, 90, 60])
    con = build(rows, NO_ADJUST)
    assert fires(con, "first_travel") == ["2019-05"]
    stake = con.execute("SELECT spend_at_stake FROM trigger_events WHERE trigger_name = 'first_travel'").fetchone()[0]
    assert stake == 250


def test_first_travel_ignores_customers_who_travel_inside_the_history_window(build):
    # Travel in month 3 could simply be the start of the data, so it is not a "first".
    rows = filler(1, 8) + monthly(1, "travel", [0, 0, 120, 0, 250, 0, 0, 0])
    assert fires(build(rows, NO_ADJUST), "first_travel") == []


def test_first_travel_boundary_is_month_four(build):
    rows = filler(1, 6) + monthly(1, "travel", [0, 0, 0, 80, 0, 0])
    assert fires(build(rows, NO_ADJUST), "first_travel") == ["2019-04"]


def test_first_travel_never_fires_for_a_customer_with_no_travel(build):
    assert fires(build(filler(1, 8), NO_ADJUST), "first_travel") == []


# --- dining cooling ------------------------------------------------------------------------

def dining(counts):
    return monthly(1, "food_dining", [20 * c for c in counts], counts=counts)


def test_dining_cooling_fires_after_two_straight_declines(build):
    rows = filler(1, 3) + dining([8, 5, 3])
    con = build(rows, NO_ADJUST)
    assert fires(con, "dining_cooling") == ["2019-03"]
    stake = con.execute("SELECT spend_at_stake FROM trigger_events WHERE trigger_name = 'dining_cooling'").fetchone()[0]
    assert stake == 100  # baseline month $160, current month $60


def test_dining_cooling_needs_both_months_down(build):
    assert fires(build(filler(1, 3) + dining([8, 5, 5]), NO_ADJUST), "dining_cooling") == []
    assert fires(build(filler(1, 3) + dining([8, 9, 3]), NO_ADJUST), "dining_cooling") == []


def test_dining_cooling_needs_a_meaningful_baseline(build):
    # 3 -> 2 -> 1 is two declines, but from a base below 4 transactions it is just noise
    assert fires(build(filler(1, 3) + dining([3, 2, 1]), NO_ADJUST), "dining_cooling") == []


def test_dining_cooling_needs_a_material_total_drop(build):
    # 8 -> 7 -> 6 is down twice but only 25% in total
    assert fires(build(filler(1, 3) + dining([8, 7, 6]), NO_ADJUST), "dining_cooling") == []
    assert fires(build(filler(1, 3) + dining([8, 6, 4]), NO_ADJUST), "dining_cooling") == ["2019-03"]


def test_dining_cooling_does_not_refire_inside_the_cooldown(build):
    # down every month: in state in months 3, 4 and 5, but only one contact
    rows = filler(1, 5) + dining([16, 10, 6, 3, 1])
    assert fires(build(rows, NO_ADJUST), "dining_cooling") == ["2019-03"]


def test_dining_cooling_ignores_a_portfolio_wide_slowdown(build):
    rows = []
    for cc in (1, 2, 3):
        rows += filler(cc, 3) + monthly(cc, "food_dining", [160, 100, 60], counts=[8, 5, 3])
    assert fires(build(rows, NO_ADJUST), "dining_cooling") == ["2019-03"]
    assert fires(build(rows, {"portfolio_adjust": 1}), "dining_cooling") == []


# --- combined table ------------------------------------------------------------------------

def test_trigger_events_has_one_row_per_customer_month_trigger(build):
    rows = (
        filler(1, 8)
        + monthly(1, "travel", [300, 300, 300, 50, 50, 50, 50, 50])
        + dining([8, 8, 8, 8, 5, 2, 2, 2])
    )
    con = build(rows, NO_ADJUST)
    dupes = con.execute(
        "SELECT count(*) FROM (SELECT customer_id, month, trigger_name FROM trigger_events GROUP BY ALL HAVING count(*) > 1)"
    ).fetchone()[0]
    assert dupes == 0
    assert fires(con, "travel_drop") == ["2019-06"]
    assert fires(con, "dining_cooling") == ["2019-06"]
    assert con.execute("SELECT min(spend_at_stake) FROM trigger_events").fetchone()[0] >= 0
