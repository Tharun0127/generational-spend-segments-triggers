"""Build docs/index.html: a self-contained interactive report for GitHub Pages."""
from __future__ import annotations

import html

import pandas as pd
import plotly.io as pio

from . import charts, config, playbook, results
from .targeting import WEAKNESSES
from .triggers import TRIGGER_LABELS

CSS = """
:root { color-scheme: light; --surface:#fcfcfb; --page:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --line:#e1e0d9; --accent:#2a78d6; --warn-bg:#fff6e0; --warn-line:#eda100; }
* { box-sizing: border-box; }
body { margin:0; background:var(--page); color:var(--ink); font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:1040px; margin:0 auto; padding:0 16px 64px; }
header.top { padding:40px 0 8px; }
h1 { font-size:30px; line-height:1.2; margin:0 0 6px; letter-spacing:-0.01em; }
h2 { font-size:22px; margin:48px 0 6px; padding-top:12px; }
h3 { font-size:16px; margin:26px 0 8px; }
p { margin:8px 0; } .lede { color:var(--ink2); max-width:760px; }
nav { position:sticky; top:0; z-index:5; background:var(--page); border-bottom:1px solid var(--line); margin:0 -16px;
  padding:10px 16px; display:flex; gap:18px; flex-wrap:wrap; font-size:14px; }
nav a { color:var(--ink2); text-decoration:none; } nav a:hover { color:var(--accent); }
.qar { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:20px 0 8px; }
.qar div, .card, .tile, .fig { background:var(--surface); border:1px solid var(--line); border-radius:10px; }
.qar div { padding:14px 16px; } .qar b { display:block; font-size:12px; text-transform:uppercase; letter-spacing:.06em;
  color:var(--muted); margin-bottom:4px; }
.note { background:var(--warn-bg); border-left:3px solid var(--warn-line); padding:12px 16px; border-radius:6px; margin:16px 0; }
.tiles { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:16px 0; }
.tile { padding:14px 16px; } .tile .v { font-size:28px; font-weight:600; line-height:1.15; }
.tile .l { color:var(--ink2); font-size:13px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px; margin:14px 0; }
.card { padding:16px; } .card h4 { margin:0 0 2px; font-size:16px; display:flex; align-items:center; gap:8px; }
.dot { width:11px; height:11px; border-radius:50%; flex:none; }
.card .sub { color:var(--ink2); font-size:13px; margin-bottom:10px; }
.kv { display:grid; grid-template-columns:1fr auto; gap:3px 12px; font-size:13.5px; }
.kv span:nth-child(odd) { color:var(--ink2); } .kv span:nth-child(even) { font-variant-numeric:tabular-nums; text-align:right; }
.card .tags { margin-top:10px; font-size:13px; color:var(--ink2); }
.genbar { display:flex; height:10px; border-radius:5px; overflow:hidden; gap:2px; margin:10px 0 4px; }
.fig { padding:6px 4px 2px; margin:14px 0; overflow:hidden; }
.fig details { margin:0 14px 10px; font-size:13px; color:var(--ink2); } .fig summary { cursor:pointer; }
ol.insights { padding-left:20px; } ol.insights li { margin:8px 0; } ol.insights b { display:block; }
.tablewrap { overflow-x:auto; margin:12px 0; }
table { border-collapse:collapse; width:100%; font-size:13.5px; background:var(--surface); }
th, td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--ink2); font-weight:600; font-size:12.5px; } td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
code, .formula { font-family:ui-monospace,Consolas,monospace; font-size:13.5px; }
.formula { background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:12px 16px; margin:12px 0; }
ul.tight li { margin:4px 0; } footer { color:var(--muted); font-size:13px; margin-top:48px; }
@media (max-width:760px) { .qar, .tiles { grid-template-columns:1fr 1fr; } .qar { grid-template-columns:1fr; } h1 { font-size:24px; } }
"""


def esc(value) -> str:
    return html.escape(str(value))


def table(df: pd.DataFrame, formats: dict | None = None, numeric: list[str] | None = None) -> str:
    formats, numeric = formats or {}, numeric or []
    head = "".join(f'<th class="{"num" if c in numeric else ""}">{esc(c)}</th>' for c in df.columns)
    body = ""
    for row in df.itertuples(index=False):
        cells = ""
        for col, val in zip(df.columns, row):
            text = formats[col].format(val) if col in formats and pd.notna(val) else ("" if pd.isna(val) else val)
            cells += f'<td class="{"num" if col in numeric else ""}">{esc(text)}</td>'
        body += f"<tr>{cells}</tr>"
    return f'<div class="tablewrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def figure_tables(d: dict) -> dict[str, str]:
    """A plain table behind each chart, so no value is reachable only by hovering."""
    pct, num = "{:.1%}", "{:,.0f}"
    s = d["gen_summary"]
    wallet = (s[s.metric.isin(config.SHARE_COLS)].pivot(index="generation", columns="metric", values="median")
              .reindex(index=config.GENERATIONS, columns=config.SHARE_COLS)
              .rename(columns=lambda c: config.CATEGORY_GROUPS[c.replace("share_", "")]).reset_index())
    bars = (s[s.metric.isin(["online_share", "monthly_txns", "median_ticket"])]
            [["generation", "n_customers", "metric", "median", "median_ci_low", "median_ci_high"]])
    tests = d["gen_tests"][["metric", "test", "effect_measure", "effect_size", "effect_within_age_band", "p_holm"]]
    prof = d["profiles"]
    trig = d["trig_monthly"].assign(month=lambda x: x.month.dt.strftime("%Y-%m"),
                                    trigger_name=lambda x: x.trigger_name.map(TRIGGER_LABELS))
    unadj = d["trig_unadjusted"].query("trigger_name == 'dining_cooling'")
    adj = d["trig_monthly"].query("trigger_name == 'dining_cooling'")
    season = pd.DataFrame({"month": adj.month.dt.strftime("%Y-%m").to_numpy(),
                           "unadjusted": unadj.customers_firing.to_numpy(),
                           "portfolio_adjusted": adj.customers_firing.to_numpy()})
    by_year = (d["features"].groupby("birth_year")
               .agg(customers=("customer_id", "size"), late_night_share=("late_night_share", "mean")).reset_index())
    return {
        "wallet_heatmap": table(wallet, {c: pct for c in wallet.columns[1:]}, list(wallet.columns[1:])),
        "generation_bars": table(bars, {c: "{:.2f}" for c in ["median", "median_ci_low", "median_ci_high"]},
                                 ["n_customers", "median", "median_ci_low", "median_ci_high"]),
        "birth_year_steps": table(by_year, {"late_night_share": pct}, ["customers", "late_night_share"]),
        "effect_sizes": table(tests, {"effect_size": "{:.3f}", "effect_within_age_band": "{:.3f}", "p_holm": "{:.2g}"},
                              ["effect_size", "effect_within_age_band", "p_holm"]),
        "k_selection": table(d["k_table"], {"inertia": num, "silhouette": "{:.3f}", "bootstrap_ari_mean": "{:.3f}",
                                            "bootstrap_ari_p05": "{:.3f}", "gmm_bic": num,
                                            "gmm_vs_kmeans_ari": "{:.3f}", "inertia_drop_pct": pct},
                             list(d["k_table"].columns)),
        "segment_index_heatmap": table(
            prof[["segment_name", "monthly_spend", "monthly_txns", "avg_ticket", *config.SHARE_COLS, "online_share",
                  "weekend_share", "late_night_share"]],
            {"monthly_spend": "${:,.0f}", "monthly_txns": "{:.0f}", "avg_ticket": "${:.0f}",
             **{c: pct for c in [*config.SHARE_COLS, "online_share", "weekend_share", "late_night_share"]}},
            ["monthly_spend", "monthly_txns", "avg_ticket", *config.SHARE_COLS, "online_share", "weekend_share",
             "late_night_share"]),
        "size_vs_spend": table(prof[["segment_name", "n_customers", "customer_share", "spend_share"]],
                               {"customer_share": pct, "spend_share": pct}, ["n_customers", "customer_share", "spend_share"]),
        "generation_mix": table(prof[["segment_name", *[f"gen_{g}" for g in config.GENERATIONS]]],
                                {f"gen_{g}": pct for g in config.GENERATIONS}, [f"gen_{g}" for g in config.GENERATIONS]),
        "generator_check": table(pd.DataFrame({"bucket": list(d["check"]["cramers_v"]),
                                               "cramers_v": list(d["check"]["cramers_v"].values())}),
                                 {"cramers_v": "{:.2f}"}, ["cramers_v"]),
        "trigger_monthly": table(trig, {"spend_at_stake": "${:,.0f}", "pct_of_customers": pct},
                                 ["customers_firing", "spend_at_stake", "pct_of_customers"]),
        "seasonality_adjustment": table(season, {}, ["unadjusted", "portfolio_adjusted"]),
        "placebo": table(d["trig_placebo"], {"placebo_fires_mean": "{:,.1f}", "actual_to_placebo_ratio": "{:.2f}"},
                         list(d["trig_placebo"].columns[1:])),
        "follow_up": table(d["trig_follow_up"], {c: "{:.2f}" for c in d["trig_follow_up"].columns[3:]},
                           list(d["trig_follow_up"].columns[2:])),
    }


def fig_html(name: str, figs: dict, tables: dict, first: bool) -> str:
    div = pio.to_html(figs[name], full_html=False, include_plotlyjs="inline" if first else False,
                      config={"displayModeBar": False, "responsive": True}, div_id=f"fig-{name}")
    data = f"<details><summary>Show the data behind this chart</summary>{tables[name]}</details>" if name in tables else ""
    return f'<div class="fig">{div}{data}</div>'


def segment_cards(d: dict) -> str:
    cards = []
    for _, p in d["profiles"].iterrows():
        color = charts.SEGMENT_COLORS[p.segment_name]
        gen_bar = "".join(
            f'<span title="{g}: {p[f"gen_{g}"]:.0%}" style="flex:{p[f"gen_{g}"]:.4f};background:{c}"></span>'
            for g, c in zip(config.GENERATIONS, charts.BLUE_RAMP) if p[f"gen_{g}"] > 0
        )
        gens = ", ".join(f"{g} {p[f'gen_{g}']:.0%}" for g in config.GENERATIONS if p[f"gen_{g}"] >= 0.005)
        cards.append(f"""
        <div class="card">
          <h4><span class="dot" style="background:{color}"></span>{esc(p.segment_name)}</h4>
          <div class="sub">{p.n_customers} customers, {p.customer_share:.0%} of the base</div>
          <div class="kv">
            <span>Share of total spend</span><span>{p.spend_share:.0%}</span>
            <span>Monthly spend</span><span>${p.monthly_spend:,.0f}</span>
            <span>Transactions per month</span><span>{p.monthly_txns:.0f}</span>
            <span>Average ticket</span><span>${p.avg_ticket:.0f}</span>
            <span>Online share</span><span>{p.online_share:.0%}</span>
            <span>Median age, % female</span><span>{p.median_age:.0f}, {p.pct_female:.0%}</span>
          </div>
          <div class="tags"><b>Top categories:</b> {esc(p.top_categories.replace(" | ", ", "))}</div>
          <div class="tags"><b>Over-indexed:</b> {esc(p.over_indexed.replace(" | ", ", "))}</div>
          <div class="genbar">{gen_bar}</div>
          <div class="tags">{esc(gens)}</div>
        </div>""")
    return f'<div class="cards">{"".join(cards)}</div>'


def build() -> str:
    d = results.load_all()
    figs = charts.build_all(d)
    tables = figure_tables(d)
    emitted = []

    def fig(name: str) -> str:
        emitted.append(name)
        return fig_html(name, figs, tables, first=len(emitted) == 1)

    f, check, art = d["features"], d["check"], d["artifact"]
    k_row = d["k_table"].set_index("k").loc[check["chosen_k"]]
    placebo = d["trig_placebo"].set_index("trigger_name")["actual_to_placebo_ratio"]
    top = {b: g.sort_values("rank").iloc[0] for b, g in d["targeting"].groupby("benefit")}
    insights = "".join(f"<li><b>{esc(i['title'])}</b>{esc(i['text'])}</li>" for i in d["insights"])

    targeting_tbl = d["targeting"][["benefit_label", "rank", "segment_name", "n_customers", "engagement", "headroom",
                                    "value", "score", "category_share_of_wallet", "category_monthly_spend"]].rename(
        columns={"benefit_label": "Benefit", "rank": "Rank", "segment_name": "Segment", "n_customers": "Customers",
                 "engagement": "Engagement", "headroom": "Headroom", "value": "Value", "score": "Score",
                 "category_share_of_wallet": "Category share of wallet", "category_monthly_spend": "Category spend / month"})
    seg_plays = pd.DataFrame(playbook.segment_plays(d)).rename(columns=lambda c: c.replace("_", " ").capitalize())
    trig_plays = pd.DataFrame(playbook.trigger_plays(d)).rename(columns=lambda c: c.replace("_", " ").capitalize())
    overlap = d["trig_overlap"].assign(trigger_a=lambda x: x.trigger_a.map(TRIGGER_LABELS),
                                       trigger_b=lambda x: x.trigger_b.map(TRIGGER_LABELS)).rename(columns={
        "trigger_a": "Trigger A", "trigger_b": "Trigger B", "same_month_both": "Same customer, same month",
        "same_month_share_of_smaller": "As share of the smaller trigger", "customers_ever_both": "Customers who ever fired both",
        "customers_ever_either": "Customers who ever fired either", "customer_jaccard": "Customer overlap (Jaccard)"})
    sens = d["trig_sensitivity"].assign(trigger_name=lambda x: x.trigger_name.map(TRIGGER_LABELS)).rename(columns={
        "variant": "Rule variant", "trigger_name": "Trigger", "fires": "Fires", "customers": "Customers",
        "share_of_fires_in_jan_to_mar": "Share of fires in Jan to Mar", "peak_month_fires": "Fires in busiest month"})
    holdout = d["trig_holdout"].assign(trigger_name=lambda x: x.trigger_name.map(TRIGGER_LABELS))[
        ["trigger_name", "fires_per_year", "treated", "holdout", "outcome_mean", "outcome_sd",
         "min_detectable_lift_pct", "fires_needed_for_10pct_lift"]].rename(columns={
        "trigger_name": "Trigger", "fires_per_year": "Fires per year", "treated": "Treated (90%)", "holdout": "Holdout (10%)",
        "outcome_mean": "Mean 3-month outcome", "outcome_sd": "Std dev", "min_detectable_lift_pct": "Smallest detectable lift",
        "fires_needed_for_10pct_lift": "Fires needed to detect 10%"})

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Generational Spend Segments and Targeting Triggers</title><style>{CSS}</style></head>
<body><main>
<header class="top">
  <h1>Generational Spend Segments and Targeting Triggers</h1>
  <p class="lede">How cardholders differ by generation and by behavior, which segments should get which benefit offer,
  and which behavior changes should trigger outreach. Built on {len(f):,} simulated cardholders and
  {f.n_txns.sum() / 1e6:.2f} million transactions from 2019 and 2020.</p>
  <div class="qar">
    <div><b>Question</b>Which cardholders should get a dining or travel credit, and when should a change in
      their behavior prompt a contact?</div>
    <div><b>Answer</b>K-means finds five stable behavior segments (bootstrap ARI {k_row.bootstrap_ari_mean:.2f}) with
      moderate separation (silhouette {k_row.silhouette:.2f}). {esc(top['travel_credit'].segment_name)} score highest
      for both credits. Generation differences are real in size but trace back to the generator's age bands.</div>
    <div><b>Recommendation</b>Test both credits on {esc(top['travel_credit'].segment_name)} first, run the travel
      drop trigger on Big-Ticket Travelers, and measure everything against a 10% holdout.</div>
  </div>
  <div class="note"><b>Read this first.</b> The data is synthetic. Its generator assigns behavior by age band, gender
  and city size, and the segments found here mostly reproduce those buckets: birth year, gender and city population
  alone predict the behavior segment for {check['demographics_only_accuracy']:.0%} of customers. Nothing below is
  evidence about real cardholders. It shows the method.</div>
</header>
<nav><a href="#generations">Generations</a><a href="#segments">Segments</a><a href="#targeting">Targeting</a>
<a href="#triggers">Triggers</a><a href="#playbook">Playbook</a><a href="#limits">Limitations</a></nav>

<div class="tiles">
  <div class="tile"><div class="v">{len(f):,}</div><div class="l">cardholders with non-fraud activity</div></div>
  <div class="tile"><div class="v">{check['chosen_k']}</div><div class="l">behavior segments, chosen from k = 3 to 8</div></div>
  <div class="tile"><div class="v">{check['demographics_only_accuracy']:.0%}</div><div class="l">of segments predictable from
    age, gender and city size alone</div></div>
  <div class="tile"><div class="v">{placebo.mean():.2f}x</div><div class="l">drop-trigger fires on real data relative to
    shuffled data</div></div>
</div>

<h2 id="generations">1. Generational insights</h2>
<p class="lede">Generations use Pew cutoffs on birth year. Each comparison is a Kruskal-Wallis or chi-square test with
an effect size. All p-values are Holm-adjusted across {len(d['gen_tests'])} tests.</p>
<h3>Five insights for a card product team</h3>
<ol class="insights">{insights}</ol>
{fig('wallet_heatmap')}
{fig('generation_bars')}
<h3>Are these generation effects, or the generator's age bands?</h3>
<p>They are the generator's age bands. Behavior steps at two birth years ({art['birth_year_cuts'][0]} and
{art['birth_year_cuts'][1]}), which do not line up with the Pew cutoffs. Silent and Boomers behave the same. Gen X is
split across two bands. Once customers are compared inside one band, the generation they belong to has a negligible
effect (median epsilon squared {art['median_effect_within_age_band']:.3f}, largest
{art['max_effect_within_age_band']:.3f}).</p>
{fig('birth_year_steps')}
{fig('effect_sizes')}

<h2 id="segments">2. Behavior segments</h2>
<p class="lede">K-means on {len(config.CLUSTER_FEATURES)} behavior features after log1p and standard scaling.
Age, gender and city size were left out of the clustering on purpose, then used to test the result.</p>
{segment_cards(d)}
{fig('k_selection')}
<p>A Gaussian mixture with {check['chosen_k']} components agrees with the K-means segments (adjusted Rand index
{k_row.gmm_vs_kmeans_ari:.2f}). A silhouette of {k_row.silhouette:.2f} means the segments overlap at the edges. It is
structure, not sharp separation.</p>
{fig('segment_index_heatmap')}
{fig('size_vs_spend')}
<h3>Do the segments just reproduce the generator's buckets?</h3>
<p>Mostly yes. A random forest given only birth year, gender and city population predicts the segment for
{check['demographics_only_accuracy']:.0%} of customers in cross-validation. Always guessing the largest segment gets
{check['majority_baseline_accuracy']:.0%}. Premium Household Shoppers are all women, Big-Ticket Travelers are almost all
men, and Digital Shoppers are the generator's youngest band. In a real portfolio, behavior segments that demographics
could predict this well would add little beyond a demographic cut.</p>
{fig('generation_mix')}
{fig('generator_check')}

<h2 id="targeting">3. Who should get which benefit</h2>
<p class="lede">Two hypothetical benefits: a monthly dining credit and an annual travel credit.</p>
<div class="formula">score = engagement x headroom x value</div>
<ul class="tight">
  <li><b>Engagement:</b> share of redemption periods in which the segment's customers already make a qualifying purchase
    (a month with any dining transaction, or a year with a travel purchase of $100 or more).</li>
  <li><b>Headroom:</b> 1 minus the customer's category share of wallet divided by the 90th percentile share across all
    customers, clipped to 0 to 1, averaged over the segment.</li>
  <li><b>Value:</b> segment mean monthly spend divided by the highest segment's mean monthly spend.</li>
</ul>
{fig('targeting_scores')}
{table(targeting_tbl, {"Engagement": "{:.2f}", "Headroom": "{:.2f}", "Value": "{:.2f}", "Score": "{:.2f}",
                        "Category share of wallet": "{:.1%}", "Category spend / month": "${:,.0f}"},
       ["Rank", "Customers", "Engagement", "Headroom", "Value", "Score", "Category share of wallet", "Category spend / month"])}
<h3>Weaknesses of this score</h3>
<ul class="tight">{"".join(f"<li>{esc(w)}</li>" for w in WEAKNESSES)}</ul>

<h2 id="triggers">4. Triggers and backtest</h2>
<p class="lede">Three rules, scored for every customer in every month of 2019 and 2020.</p>
{table(trig_plays[["Trigger", "Rule", "Backtest"]])}
{fig('trigger_monthly')}
<h3>Why the rules are measured relative to the portfolio</h3>
{fig('seasonality_adjustment')}
{table(sens, {"Share of fires in Jan to Mar": "{:.0%}", "Fires": "{:,.0f}"},
       ["Fires", "Customers", "Share of fires in Jan to Mar", "Fires in busiest month"])}
<h3>Overlap between triggers</h3>
{table(overlap, {"As share of the smaller trigger": "{:.1%}", "Customer overlap (Jaccard)": "{:.2f}"},
       list(overlap.columns[2:]))}
<h3>Are the triggers finding real change?</h3>
<p>Not in this data. The generator has no customers whose behavior actually shifts, so a drop trigger can only catch
random month-to-month variation. Two checks show it.</p>
{fig('placebo')}
{fig('follow_up')}
<p>The second chart is the reason for a holdout. Customers who fire a drop trigger were coming off an unusually high
period and go back to their usual level on their own. A before-and-after comparison would hand that recovery to the offer.</p>
<h3>Offer, channel, success metric and holdout for each trigger</h3>
{table(trig_plays[["Trigger", "Offer", "Channel", "Success metric"]])}
<p><b>Holdout design.</b> {esc(playbook.HOLDOUT_DESIGN)} Randomize the first time a customer fires, keep them in that
arm for later fires, and stratify by segment.</p>
{table(holdout, {"Mean 3-month outcome": "${:,.0f}", "Std dev": "${:,.0f}", "Smallest detectable lift": "{:.0%}",
                 "Fires needed to detect 10%": "{:,.0f}"}, list(holdout.columns[1:]))}
<p>Smallest detectable lift is for a two-sided 5% test at 80% power. With about 900 customers, only dining cooling is
close to testable. At the scale of a real card portfolio the required volumes are reached within weeks.</p>

<h2 id="playbook">5. Playbook</h2>
{table(seg_plays)}

<h2 id="limits">6. Limitations</h2>
<ul class="tight">
  <li>Synthetic data. Customers do not churn, join, or change behavior, and every customer has the same seasonality.</li>
  <li>{len(f):,} customers. Gen Z has {int((f.generation == 'Gen Z').sum())} and Digital Shoppers
    {int((f.segment_name == 'Digital Shoppers').sum())}, so their estimates are noisy.</li>
  <li>Generation and segment differences come from the generator's age, gender and city-size profiles.</li>
  <li>Only three category pairs carry a channel tag, so online share covers part of the wallet.</li>
  <li>No account open dates, credit lines, balances, fees, rewards cost or offer response, so no profit view and no
    causal claim.</li>
  <li>The targeting score and the trigger thresholds are choices, not estimates. The report shows how results move
    when the thresholds change.</li>
</ul>
<footer>Built with DuckDB, scikit-learn and Plotly. Source data: Kaggle kartik2112/fraud-detection (Sparkov generator).
Fraud transactions are excluded from every number on this page.</footer>
</main></body></html>"""

    config.DOCS_DIR.mkdir(exist_ok=True)
    (config.DOCS_DIR / "index.html").write_text(page, encoding="utf-8")
    print(f"Wrote docs/index.html ({len(page) / 1e6:.1f} MB, {len(emitted)} charts)")
    return page


if __name__ == "__main__":
    build()
