"""Write notebooks/analysis.ipynb and execute it so the outputs are saved in the file."""
from __future__ import annotations

import nbformat
from nbclient import NotebookClient
from nbformat.v4 import new_code_cell as code
from nbformat.v4 import new_markdown_cell as md
from nbformat.v4 import new_notebook

from . import config

NOTEBOOK_PATH = config.ROOT / "notebooks" / "analysis.ipynb"

CELLS = [
    md("""# Generational Spend Segments and Targeting Triggers

**Business question.** How do cardholders differ by generation and by behavior, which segments should get which
benefit offers, and which behavior changes should trigger outreach?

**Data.** Kaggle `kartik2112/fraud-detection`: simulated card transactions for 2019 and 2020. Fraud rows are excluded.

**How to read this notebook.** The heavy lifting happens in `sql/` and `src/` and is rebuilt by `run_all.py`.
This notebook reads those results and walks through them in order. Every number shown is computed in a cell,
not typed by hand.

**Honesty rule.** The data is synthetic. A generator assigned each customer a profile built from age band, gender
and city size. Sections 3 and 4 test how much of what we find is just that profile, and say so."""),
    code("""import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent))

import pandas as pd
import plotly.io as pio
from IPython.display import Markdown, display

from src import charts, config, db, playbook, results
from src.targeting import WEAKNESSES

pio.renderers.default = "png"          # static images, so charts show on GitHub
pio.renderers["png"].width = 980
pio.renderers["png"].scale = 2
pd.set_option("display.max_columns", 40)
pd.set_option("display.float_format", lambda v: f"{v:,.3f}")

d = results.load_all()
figs = charts.build_all(d)
f = d["features"]
con = db.connect(read_only=True)
say = lambda text: display(Markdown(text))"""),

    md("""## 1. The data

Two CSV files are combined in DuckDB. `cc_num` is the customer key because the data has no customer id."""),
    code("""overview = con.execute('''
    SELECT count(*) AS raw_rows, sum(is_fraud) AS fraud_rows, count(DISTINCT cc_num) AS cards,
           min(trans_ts) AS first_ts, max(trans_ts) AS last_ts
    FROM raw_transactions''').df()
clean = con.execute("SELECT count(*) AS rows, count(DISTINCT customer_id) AS customers, sum(amt) AS spend FROM transactions").df()
display(overview, clean)
say(f"**{overview.raw_rows[0]:,} rows** in the two files. After removing {overview.fraud_rows[0]:,.0f} fraud rows, "
    f"**{clean.rows[0]:,} transactions from {clean.customers[0]} customers** remain. "
    f"{overview.cards[0] - clean.customers[0]} cards had only fraud transactions and drop out.")"""),
    code("""con.execute('''
    SELECT category_group, count(*) AS txns, round(sum(amt)) AS spend,
           round(100 * sum(amt) / sum(sum(amt)) OVER (), 1) AS pct_of_spend,
           round(avg(amt), 2) AS avg_ticket, round(median(amt), 2) AS median_ticket
    FROM transactions GROUP BY 1 ORDER BY spend DESC''').df()"""),
    md("""Three things about this data would not be true of a real portfolio. They matter for everything after.
The full profile is in `docs/data_profile.md`."""),
    code("""tiers = f.groupby("txns_per_day_tier").agg(customers=("customer_id", "size"), min_txns=("n_txns", "min"), max_txns=("n_txns", "max"))
display(tiers)
season = con.execute("SELECT month, sum(spend) AS spend FROM customer_month GROUP BY 1 ORDER BY 1").df()
season["index_vs_average_month"] = season.spend / season.spend.mean()
say(f"1. **Transaction counts come in fixed tiers** of 1 to 6 a day (table above). Nothing in between.\\n"
    f"2. **Nobody churns.** All {len(f)} customers are active in all {f.active_months.max()} months. "
    f"Recency is {f.recency_days.min()} to {f.recency_days.max()} days for everyone, so it is not used for clustering.\\n"
    f"3. **Everyone shares one seasonal pattern.** December runs at {season.index_vs_average_month.max():.2f}x an "
    f"average month and the lowest month at {season.index_vs_average_month.min():.2f}x.")"""),

    md("""## 2. Features, built in SQL

Per-customer features come from five SQL files run in DuckDB (`sql/02` to `sql/05`): RFM, average ticket, share of
wallet across 8 category groups, online share, weekend and late-night share, spend volatility and
quarter-over-quarter trends. The trend step uses `LAG` window functions:"""),
    code("""print((config.SQL_DIR / "04_customer_quarter.sql").read_text())"""),
    code("""con.execute('''
    SELECT quarter, round(spend) AS spend, round(prev_q_spend) AS prev_q_spend,
           round(qoq_spend_change, 3) AS qoq_change, round(yoy_spend_change, 3) AS yoy_change
    FROM customer_quarter
    WHERE customer_id = (SELECT min(customer_id) FROM customer_quarter)
    ORDER BY quarter''').df()"""),
    code("""f[config.CLUSTER_FEATURES + ["recency_days", "avg_qoq_spend_change", "avg_yoy_spend_change"]].describe().T[["mean", "std", "min", "50%", "max"]]"""),

    md("""## 3. Generational insights

Generations use Pew cutoffs on birth year. Each metric gets a Kruskal-Wallis test (or chi-square for categorical
outcomes) and an effect size. With 900 customers almost everything is "significant", so the effect size is the
number to read: epsilon squared of 0.01 is small, 0.06 medium, 0.14 large."""),
    code("""display(f.generation.value_counts().reindex(config.GENERATIONS).to_frame("customers").T)
d["gen_tests"][["metric", "test", "effect_measure", "effect_size", "effect_label", "p_holm", "effect_within_age_band"]]"""),
    code("""say("**Five insights a card product team could act on**\\n\\n" + "\\n".join(f"{i}. **{x['title']}.** {x['text']}" for i, x in enumerate(d["insights"], 1)))"""),
    code("""figs["wallet_heatmap"].show()"""),
    code("""figs["generation_bars"].show()"""),
    md("""### Are these generation effects, or the generator's age bands?

If generations mattered in their own right, behavior would change at the Pew cutoffs. It does not. It changes at
two other birth years."""),
    code("""figs["birth_year_steps"].show()"""),
    code("""a = d["artifact"]
display(pd.DataFrame(a["generation_by_band"]).T)
say(f"A three-leaf regression tree on birth year puts the steps at **{a['birth_year_cuts'][0]}** and "
    f"**{a['birth_year_cuts'][1]}**. Silent and Boomers sit in the same band. Gen X is split across two. "
    f"The test that settles it: compare generations **inside** one band. The median effect size falls from "
    f"{a['median_effect_by_generation']:.3f} to **{a['median_effect_within_age_band']:.3f}** "
    f"(largest {a['max_effect_within_age_band']:.3f}). The generational differences above are real in size, "
    f"but they are the generator's age bands seen through Pew labels.")"""),
    code("""figs["effect_sizes"].show()"""),

    md("""## 4. Behavior segments

K-means on 16 behavior features after `log1p` and standard scaling. Age, gender and city size are **not** inputs.
They are held back to test the result.

**Choosing k.** Four things are weighed: silhouette, the inertia elbow, stability under bootstrap resampling
(adjusted Rand index against the full-data labels, 100 resamples) and whether the segments tell different
business stories."""),
    code("""display(d["k_table"])
figs["k_selection"].show()"""),
    code("""k = d["k_table"].set_index("k")
chosen = d["check"]["chosen_k"]
say(f"**k = {chosen}.** It has the highest silhouette ({k.loc[chosen, 'silhouette']:.3f}) and a mean bootstrap ARI of "
    f"{k.loc[chosen, 'bootstrap_ari_mean']:.2f} (5th percentile {k.loc[chosen, 'bootstrap_ari_p05']:.2f}). "
    f"k = 4 is slightly more stable ({k.loc[4, 'bootstrap_ari_mean']:.2f}) but merges travelers with high-spend "
    f"household shoppers, which are opposite targets for a travel credit. From k = 6 stability drops "
    f"({k.loc[6, 'bootstrap_ari_mean']:.2f}). Inertia has no sharp elbow. A Gaussian mixture with {chosen} components "
    f"gives nearly the same segments (ARI {k.loc[chosen, 'gmm_vs_kmeans_ari']:.2f} against K-means), so the result does "
    f"not depend on K-means' assumptions. A silhouette near {k.loc[chosen, 'silhouette']:.1f} is moderate: the segments "
    f"overlap at the edges.")"""),
    md("""### Segment profile cards"""),
    code("""cards = d["profiles"].set_index("segment_name")[["n_customers", "customer_share", "spend_share", "monthly_spend",
    "monthly_txns", "avg_ticket", "online_share", "median_age", "pct_female", "top_categories", "over_indexed"]]
display(cards.T)
display(d["profiles"].set_index("segment_name")[[f"gen_{g}" for g in config.GENERATIONS]].rename(columns=lambda c: c[4:]).style.format("{:.0%}"))"""),
    code("""figs["segment_index_heatmap"].show()"""),
    code("""figs["size_vs_spend"].show()"""),
    md("""### Do the segments just reproduce the generator's buckets?"""),
    code("""c = d["check"]
display(pd.Series(c["cramers_v"], name="Cramer's V with segment").sort_values(ascending=False).to_frame())
display(pd.crosstab(f.segment_name, f.age_band), pd.crosstab(f.segment_name, f.gender))
say(f"**Mostly yes.** A random forest that sees only birth year, gender and city population predicts the behavior "
    f"segment for **{c['demographics_only_accuracy']:.1%}** of customers (5-fold cross-validation). Always guessing the "
    f"largest segment gets {c['majority_baseline_accuracy']:.1%}. The clustering never saw those three variables, so it "
    f"has rediscovered the generator's customer profiles. In a real portfolio this would be a warning that the "
    f"behavior segments add little beyond a demographic cut.")"""),
    code("""figs["generation_mix"].show()"""),
    code("""figs["generator_check"].show()"""),

    md("""## 5. Who should get which benefit

Two hypothetical benefits: a monthly dining credit and an annual travel credit.

`score = engagement x headroom x value`

- **engagement**: share of redemption periods in which the segment's customers already make a qualifying purchase
  (months with any dining transaction; years with a travel purchase of $100 or more)
- **headroom**: 1 minus the customer's category share of wallet divided by the 90th percentile share across all
  customers, clipped to 0..1, averaged over the segment
- **value**: segment mean monthly spend divided by the highest segment's mean monthly spend"""),
    code("""display(d["targeting"][["benefit_label", "rank", "segment_name", "n_customers", "engagement", "headroom", "value", "score",
                        "category_share_of_wallet", "category_monthly_spend"]])
figs["targeting_scores"].show()"""),
    code("""say("**Weaknesses of this score**\\n\\n" + "\\n".join(f"- {w}" for w in WEAKNESSES))"""),

    md("""## 6. Triggers

Three rules, defined in `sql/06_triggers.sql` and scored for every customer in every month."""),
    code("""plays = pd.DataFrame(playbook.trigger_plays(d))
with pd.option_context("display.max_colwidth", None):
    display(plays[["trigger", "rule"]])
display(d["trig_summary"])
figs["trigger_monthly"].show()"""),
    md("""### Shared seasonality would break a naive rule

Comparing a customer only with their own past makes the whole portfolio look like it is declining after December.
The rules therefore measure each customer against what the portfolio did over the same months."""),
    code("""figs["seasonality_adjustment"].show()
d["trig_sensitivity"]"""),
    md("""### Overlap between triggers"""),
    code("""d["trig_overlap"]"""),
    md("""### Are the triggers finding real change?

Two checks. First, a placebo: remove seasonality, shuffle each customer's months into random order, and run the
same rules. Shuffling keeps each customer's level and noise but destroys any sustained decline. Second, a follow-up:
what do fired customers do next, with no offer sent?"""),
    code("""figs["placebo"].show()
d["trig_placebo"]"""),
    code("""figs["follow_up"].show()
d["trig_follow_up"]"""),
    code("""p = d["trig_placebo"].set_index("trigger_name").actual_to_placebo_ratio
fu = d["trig_follow_up"].query("scope == 'All customers'").set_index("trigger_name")
say(f"**Not in this data.** The drop triggers fire {p['travel_drop']:.2f}x and {p['dining_cooling']:.2f}x as often on the "
    f"real month order as on shuffled months, which is no difference. The generator has no customers whose behavior "
    f"actually shifts. The follow-up shows why: the baseline window was an unusually high period "
    f"(the long-run average is {fu.loc['travel_drop', 'long_run_index']:.2f} of baseline for travel and "
    f"{fu.loc['dining_cooling', 'long_run_index']:.2f} for dining), and after firing customers return to that usual "
    f"level on their own ({fu.loc['travel_drop', 'follow_up_index']:.2f} and {fu.loc['dining_cooling', 'follow_up_index']:.2f}). "
    f"This is regression to the mean. The backtest validates volume and mechanics. It cannot validate usefulness.")"""),
    md("""### Offer, channel, success metric and holdout

Because fired customers recover on their own, a before-and-after comparison would credit the offer with that
recovery. Each trigger therefore gets a randomized 10% holdout."""),
    code("""with pd.option_context("display.max_colwidth", None):
    display(plays[["trigger", "offer", "channel", "success_metric"]])
say(f"**Design.** {playbook.HOLDOUT_DESIGN} Randomize the first time a customer fires, keep them in that arm for "
    f"later fires, and stratify by segment.")
d["trig_holdout"]"""),
    code("""h = d["trig_holdout"].set_index("trigger_name")
say(f"With this portfolio's volume, the dining cooling test could detect a lift of "
    f"{h.loc['dining_cooling', 'min_detectable_lift_pct']:.0%} or more and the travel drop test only "
    f"{h.loc['travel_drop', 'min_detectable_lift_pct']:.0%} or more, because travel spend is so lumpy "
    f"(standard deviation ${h.loc['travel_drop', 'outcome_sd']:,.0f} on a mean of ${h.loc['travel_drop', 'outcome_mean']:,.0f}). "
    f"Detecting a 10% lift needs about {h.loc['dining_cooling', 'fires_needed_for_10pct_lift']:,} dining fires or "
    f"{h.loc['travel_drop', 'fires_needed_for_10pct_lift']:,} travel fires. A real card portfolio reaches that quickly. "
    f"This one cannot.")"""),

    md("""## 7. Playbook and limitations"""),
    code("""with pd.option_context("display.max_colwidth", None):
    display(pd.DataFrame(playbook.segment_plays(d)))"""),
    code("""c, a = d["check"], d["artifact"]
say(f'''**What this project can and cannot claim**

- It shows a working method: SQL features, tested generational comparisons, a stability-checked segmentation,
  a transparent targeting score and backtested triggers with a measurement plan.
- It does not show anything about real cardholders. The data is synthetic.
- Generational differences are the generator's age bands (effect inside a band: {a["median_effect_within_age_band"]:.3f}).
- The segments mostly reproduce generator profiles ({c["demographics_only_accuracy"]:.0%} predictable from age, gender and city size).
- The drop triggers fire at the rate of random noise, because no simulated customer ever changes behavior.
- {len(f)} customers is small. Gen Z has {int((f.generation == "Gen Z").sum())} customers.
- There is no offer response data, so the targeting ranking and the trigger offers are hypotheses to test with a holdout.''')
con.close()"""),
]


def build(execute: bool = True) -> None:
    nb = new_notebook(cells=CELLS, metadata={
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    })
    NOTEBOOK_PATH.parent.mkdir(exist_ok=True)
    if execute:
        NotebookClient(nb, timeout=600, kernel_name="python3",
                       resources={"metadata": {"path": str(NOTEBOOK_PATH.parent)}}).execute()
    nbformat.write(nb, NOTEBOOK_PATH)
    print(f"Wrote {NOTEBOOK_PATH.relative_to(config.ROOT)}" + (" (executed)" if execute else ""))


if __name__ == "__main__":
    build()
