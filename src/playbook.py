"""Turn the results into a one-page targeting playbook.

The plays are written here once and used by both docs/targeting_playbook.md and
docs/index.html. Every number is read from outputs/.
"""
from __future__ import annotations

import pandas as pd

from . import config, results
from .targeting import WEAKNESSES
from .triggers import TRIGGER_LABELS, TRIGGERS


def trigger_rules(params: dict) -> dict[str, str]:
    return {
        "travel_drop": (
            f"Travel spend over the last 3 months is more than {params['travel_drop_pct']:.0%} below the 3 months "
            f"before, after allowing for the portfolio-wide change, from a base of at least "
            f"${params['travel_min_base']:,.0f}."
        ),
        "first_travel": (
            f"First-ever travel transaction, after at least {params['first_travel_min_history']} months on the "
            f"card with no travel."
        ),
        "dining_cooling": (
            f"Dining transaction count down two months in a row relative to the portfolio, from a base of at least "
            f"{params['dining_min_base']} a month, with a total fall of {params['dining_min_drop']:.0%} or more."
        ),
    }


TRIGGER_PLAYS = {
    "travel_drop": {
        "offer": "Bonus points or a statement credit on the next travel booking made within 60 days.",
        "channel": "Email plus an in-app message. One contact, then silence for the cooldown period.",
        "success_metric": "Travel spend per customer in the 3 months after the trigger fires.",
    },
    "first_travel": {
        "offer": "Introduce the annual travel credit and add extra points on travel for 90 days.",
        "channel": "App push within two days of the purchase, followed by one email.",
        "success_metric": "Share of customers who make a second travel purchase within 90 days, and travel spend "
                          "over the same 3 months.",
    },
    "dining_cooling": {
        "offer": "Reminder of the monthly dining credit, or a one-time dining bonus for customers without it.",
        "channel": "App push or email early in the following month, when the monthly credit resets.",
        "success_metric": "Dining transactions and dining spend per customer in the 3 months after the trigger fires.",
    },
}


HOLDOUT_DESIGN = (
    f"Each month, hold back a random {config.HOLDOUT_SHARE:.0%} of the customers who fire and send them nothing. "
    "Compare treated with holdout on the success metric. Never compare before with after, because customers "
    "drift back to their usual level on their own."
)


def holdout_text(row: pd.Series) -> str:
    return (
        f"About {row.fires_per_year} fires a year in the backtest, {row.holdout} in holdout. At that volume the smallest "
        f"lift the test can detect is {row.min_detectable_lift_pct:.0%}. Detecting a 10% lift needs about "
        f"{row.fires_needed_for_10pct_lift:,} fires."
    )


def segment_plays(d: dict) -> list[dict]:
    prof = d["profiles"].set_index("segment_name")
    score = d["targeting"].set_index(["segment_name", "benefit"])
    by_seg = d["trig_by_segment"].set_index(["segment_name", "trigger_name"])
    dining_share = d["targeting"].query("benefit == 'dining_credit'").set_index("segment_name")["category_share_of_wallet"]

    def rank(seg, benefit):
        r = score.loc[(seg, benefit)]
        return f"rank {int(r['rank'])} of 5, score {r.score:.2f}"

    def fired(seg, trig):
        r = by_seg.loc[(seg, trig)]
        return f"{int(r.customers)} customers fired it in the backtest"

    plays = [
        {
            "segment": "Premium Household Shoppers",
            "offer": f"Lead with the annual travel credit ({rank('Premium Household Shoppers', 'travel_credit')}) "
                     f"and add the monthly dining credit ({rank('Premium Household Shoppers', 'dining_credit')}).",
            "why": f"Highest spend per customer (${prof.loc['Premium Household Shoppers', 'monthly_spend']:,.0f} a "
                   f"month) with only {prof.loc['Premium Household Shoppers', 'share_travel']:.1%} of wallet in travel.",
            "trigger": f"First travel ({fired('Premium Household Shoppers', 'first_travel')}) and dining cooling "
                       f"({fired('Premium Household Shoppers', 'dining_cooling')}).",
            "success_metric": "Travel and dining spend per customer against holdout.",
        },
        {
            "segment": "Big-Ticket Travelers",
            "offer": f"Use the travel credit to defend spend, not to grow it "
                     f"({rank('Big-Ticket Travelers', 'travel_credit')} on the growth score because travel is already "
                     f"{prof.loc['Big-Ticket Travelers', 'share_travel']:.0%} of wallet).",
            "why": "The only segment where travel is a habit, so a fall in travel is worth a contact.",
            "trigger": f"Travel drop ({fired('Big-Ticket Travelers', 'travel_drop')}, "
                       f"${by_seg.loc[('Big-Ticket Travelers', 'travel_drop'), 'spend_at_stake']:,.0f} at stake).",
            "success_metric": "Travel spend in the 3 months after the trigger against holdout.",
        },
        {
            "segment": "Digital Shoppers",
            "offer": f"Monthly dining credit ({rank('Digital Shoppers', 'dining_credit')}), delivered in the app.",
            "why": f"Most online segment ({prof.loc['Digital Shoppers', 'online_share']:.0%} of channel-tagged spend) "
                   f"and the most frequent ({prof.loc['Digital Shoppers', 'monthly_txns']:.0f} transactions a month).",
            "trigger": f"Dining cooling ({fired('Digital Shoppers', 'dining_cooling')}).",
            "success_metric": "Months with a dining transaction and dining spend against holdout.",
        },
        {
            "segment": "Mainstream Everyday Spenders",
            "offer": f"Annual travel credit as a test cell ({rank('Mainstream Everyday Spenders', 'travel_credit')}). "
                     f"No dining credit yet ({rank('Mainstream Everyday Spenders', 'dining_credit')}).",
            "why": f"Largest segment ({prof.loc['Mainstream Everyday Spenders', 'customer_share']:.0%} of customers), "
                   f"so even a small lift adds up, but spend per customer is average.",
            "trigger": f"First travel ({fired('Mainstream Everyday Spenders', 'first_travel')}).",
            "success_metric": "Share with a travel purchase of $100 or more in the year against holdout.",
        },
        {
            "segment": "Light Home and Dining Spenders",
            "offer": f"No new credit ({rank('Light Home and Dining Spenders', 'dining_credit')} for dining, "
                     f"{rank('Light Home and Dining Spenders', 'travel_credit')} for travel).",
            "why": f"Lowest spend (${prof.loc['Light Home and Dining Spenders', 'monthly_spend']:,.0f} a month) and "
                   f"dining already takes {dining_share['Light Home and Dining Spenders']:.1%} of it, against "
                   f"{dining_share.drop('Light Home and Dining Spenders').max():.1%} or less elsewhere, so a credit "
                   f"would mostly pay for existing spend.",
            "trigger": f"Dining cooling as a low-cost retention message "
                       f"({fired('Light Home and Dining Spenders', 'dining_cooling')}).",
            "success_metric": "Dining transactions in the 3 months after the trigger against holdout.",
        },
    ]
    return plays


def trigger_plays(d: dict) -> list[dict]:
    rules = trigger_rules(d["trig_params"])
    summary = d["trig_summary"].set_index("trigger_name")
    holdout = d["trig_holdout"].set_index("trigger_name")
    rows = []
    for trig in TRIGGERS:
        s = summary.loc[trig]
        rows.append({
            "trigger": TRIGGER_LABELS[trig],
            "rule": rules[trig],
            "backtest": f"{int(s.fires):,} fires from {int(s.customers)} customers "
                        f"({s.pct_customers_ever_firing:.0%} of the base), ${s.spend_at_stake:,.0f} at stake.",
            **TRIGGER_PLAYS[trig],
            "holdout": holdout_text(holdout.loc[trig]),
        })
    return rows


def render_markdown(d: dict) -> str:
    seg = segment_plays(d)
    trig = trigger_plays(d)
    check = d["check"]
    placebo = d["trig_placebo"].set_index("trigger_name")["actual_to_placebo_ratio"]
    overlap = d["trig_overlap"].set_index(["trigger_a", "trigger_b"]).loc[("travel_drop", "dining_cooling")]

    lines = [
        "# Targeting playbook",
        "",
        "One page: which segment gets which offer, what triggers the contact, and how to know it worked.",
        "Built on synthetic data, so treat it as a test plan, not as proven results.",
        "",
        "## Segment plays",
        "",
        "| Segment | Offer | Why | Trigger | Success metric |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| **{p['segment']}** | {p['offer']} | {p['why']} | {p['trigger']} | {p['success_metric']} |" for p in seg]
    lines += [
        "",
        "## Trigger plays",
        "",
        "| Trigger | Rule | Backtest (2019 and 2020) | Offer | Channel | Success metric |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| **{t['trigger']}** | {t['rule']} | {t['backtest']} | {t['offer']} | {t['channel']} | {t['success_metric']} |"
        for t in trig
    ]
    lines += ["", "## How to measure", "", f"- **Design.** {HOLDOUT_DESIGN}"]
    lines += [f"- **{t['trigger']}.** {t['holdout']}" for t in trig]
    lines += [
        "- **Assignment.** Randomize at the customer level the first time a customer fires, and keep the customer "
        "in the same arm for later fires. Stratify by segment so both arms have the same mix.",
        f"- **Contact rules.** Travel drop and dining cooling fired for the same customer in the same month "
        f"{int(overlap.same_month_both)} times in the backtest. When that happens, send the travel offer only, "
        f"because it has more spend at stake.",
        "- **Read-out.** Report lift as treated minus holdout with a confidence interval, per trigger and per "
        "segment. Use pre-trigger spend as a covariate to narrow the interval.",
        "",
        "## What to keep in mind",
        "",
        f"- The segments are not independent of demographics. Birth year, gender and city size predict the segment for "
        f"{check['demographics_only_accuracy']:.0%} of customers. The generator built them that way.",
        f"- In this data the drop triggers fire about as often on shuffled months as on real ones "
        f"({placebo['travel_drop']:.2f}x and {placebo['dining_cooling']:.2f}x). The backtest shows volume and "
        f"mechanics. It does not show that the triggers find customers who are really changing.",
        "- The targeting score ranks segments for growth. " + WEAKNESSES[1],
        "- Spend at stake is the gap to an expected level, not money an offer would recover.",
        "",
    ]
    return "\n".join(lines)


def run() -> str:
    text = render_markdown(results.load_all())
    (config.DOCS_DIR / "targeting_playbook.md").write_text(text, encoding="utf-8")
    print("Wrote docs/targeting_playbook.md")
    return text


if __name__ == "__main__":
    print(run())
