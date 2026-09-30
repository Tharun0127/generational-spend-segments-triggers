"""Plotly figures shared by the HTML report and the notebook.

Every figure takes the dictionary from results.load_all() and builds its title from the
data, so a title can never drift away from the numbers it describes.
"""
from __future__ import annotations

import textwrap

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import config
from .triggers import TRIGGER_LABELS, TRIGGERS

# Palette: categorical slots in a fixed order, one blue ramp for ordered groups.
SURFACE = "#fcfcfb"
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
GRAY = "#c3c2b7"
BLUE_RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]  # oldest to youngest generation
SEQUENTIAL = [[0.0, "#cde2fb"], [0.5, "#3987e5"], [1.0, "#0d366b"]]
DIVERGING = [[0.0, "#d03b3b"], [0.25, "#ecb1a8"], [0.5, "#f0efec"], [0.75, "#9ec5f4"], [1.0, "#1c5cab"]]

# Color follows the segment, not its rank. Order is segment_id (highest spend first).
SEGMENT_ORDER = [
    "Premium Household Shoppers",
    "Big-Ticket Travelers",
    "Digital Shoppers",
    "Mainstream Everyday Spenders",
    "Light Home and Dining Spenders",
]
SEGMENT_COLORS = dict(zip(SEGMENT_ORDER, [BLUE, ORANGE, AQUA, YELLOW, MAGENTA]))
TRIGGER_COLORS = dict(zip(TRIGGERS, [BLUE, ORANGE, AQUA]))
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def _title(text: str, subtitle: str = "", width: int = 92) -> dict:
    lines = "<br>".join(textwrap.wrap(text, width))
    if subtitle:
        sub = "<br>".join(textwrap.wrap(subtitle, int(width * 1.3)))
        lines += f'<br><span style="font-size:12.5px;color:{INK_2};font-weight:400">{sub}</span>'
    return {"text": lines, "x": 0, "xanchor": "left", "xref": "container", "yref": "container",
            "pad": {"l": 16, "t": 14}, "y": 1, "yanchor": "top", "font": {"size": 16.5, "color": INK}}


def _style(fig: go.Figure, title: str, subtitle: str = "", height: int = 420, top: int = 105, **layout) -> go.Figure:
    fig.update_layout(
        title=_title(title, subtitle),
        height=height,
        margin={"l": 16, "r": 24, "t": top, "b": 40},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font={"family": FONT, "size": 12.5, "color": INK_2},
        hoverlabel={"bgcolor": "white", "font": {"family": FONT, "size": 12.5, "color": INK}, "bordercolor": GRID},
        legend={"orientation": "h", "x": 0, "y": 1.0, "yanchor": "bottom", "font": {"color": INK_2},
                "bgcolor": "rgba(0,0,0,0)"},
        bargap=0.45,
        **layout,
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, tickcolor=AXIS, zeroline=False, automargin=True,
                     tickfont={"color": MUTED})
    fig.update_yaxes(gridcolor=GRID, gridwidth=1, linecolor=SURFACE, zeroline=False, automargin=True,
                     tickfont={"color": MUTED})
    return fig


def _subplots(**kwargs) -> go.Figure:
    fig = make_subplots(**kwargs)
    fig.update_annotations(font={"size": 13, "color": INK_2})  # subplot titles
    return fig


def _horizontal(fig: go.Figure) -> go.Figure:
    """Horizontal bars: grid runs vertically, category labels in ink."""
    fig.update_xaxes(showgrid=True, gridcolor=GRID, linecolor=SURFACE)
    fig.update_yaxes(showgrid=False, linecolor=AXIS, tickfont={"color": INK_2})
    return fig


def _gen_median(d: dict, metric: str) -> pd.DataFrame:
    s = d["gen_summary"]
    return s[s["metric"] == metric].set_index("generation").reindex(config.GENERATIONS)


# ------------------------------------------------------------------------------ generations

def wallet_heatmap(d: dict) -> go.Figure:
    s = d["gen_summary"]
    shares = s[s["metric"].isin(config.SHARE_COLS)].pivot(index="generation", columns="metric", values="median")
    shares = shares.reindex(index=config.GENERATIONS[::-1], columns=config.SHARE_COLS)
    n = s.drop_duplicates("generation").set_index("generation")["n_customers"]
    labels = ["<br>".join(textwrap.wrap(config.CATEGORY_GROUPS[c.replace("share_", "")], 14)) for c in shares.columns]
    fig = go.Figure(go.Heatmap(
        z=shares.to_numpy() * 100, x=labels, y=[f"{g} (n={n[g]})" for g in shares.index],
        colorscale=SEQUENTIAL, zmin=0, zmax=25, xgap=2, ygap=2,
        texttemplate="%{z:.0f}%", textfont={"size": 13},
        colorbar={"title": {"text": "Share of wallet", "side": "right"}, "ticksuffix": "%", "thickness": 10, "len": 0.8},
        customdata=[[config.CATEGORY_GROUPS[c.replace("share_", "")] for c in shares.columns]] * len(shares),
        hovertemplate="%{y}<br>%{customdata}: %{z:.1f}% of spend<extra></extra>",
    ))
    z, b = shares.loc["Gen Z"], shares.loc["Boomers"]
    title = (f"Gen Z puts {z['share_shopping']:.0%} of spend into shopping and {z['share_grocery']:.0%} into grocery; "
             f"Boomers put {b['share_shopping']:.0%} into shopping and {b['share_grocery']:.0%} into grocery")
    fig = _style(fig, title, "Median share of wallet per customer, by generation and category group", height=380, top=80)
    fig.update_xaxes(side="bottom", tickangle=0, tickfont={"color": INK_2, "size": 11.5})
    fig.update_yaxes(tickfont={"color": INK_2})
    return fig


def generation_bars(d: dict) -> go.Figure:
    panels = [("online_share", "Online share of channel-tagged spend", 100, "%{y:.0f}%", "{:.0f}%"),
              ("monthly_txns", "Transactions per month", 1, "%{y:.0f}", "{:.0f}"),
              ("median_ticket", "Median ticket ($)", 1, "$%{y:.0f}", "${:.0f}")]
    fig = _subplots(rows=1, cols=3, subplot_titles=[p[1] for p in panels], horizontal_spacing=0.07)
    for i, (metric, _, scale, fmt, label) in enumerate(panels, start=1):
        m = _gen_median(d, metric)
        y = m["median"] * scale
        fig.add_trace(go.Bar(
            x=m.index, y=y, marker={"color": BLUE, "cornerradius": 4}, showlegend=False,
            error_y={"type": "data", "symmetric": False, "array": (m["median_ci_high"] * scale - y),
                     "arrayminus": (y - m["median_ci_low"] * scale), "color": INK_2, "thickness": 1, "width": 3},
            text=[label.format(v) for v in y], textposition="inside", insidetextanchor="start",
            textangle=0, textfont={"color": "white", "size": 12},
            customdata=np.stack([m["median_ci_low"] * scale, m["median_ci_high"] * scale, m["n_customers"]], axis=1),
            hovertemplate="%{x} (n=%{customdata[2]})<br>Median " + fmt
                          + "<br>95% interval %{customdata[0]:.1f} to %{customdata[1]:.1f}<extra></extra>",
        ), row=1, col=i)
        fig.update_yaxes(rangemode="tozero", row=1, col=i)
    on, tx, tk = (_gen_median(d, m)["median"] for m in ("online_share", "monthly_txns", "median_ticket"))
    title = (f"Gen Z is the most online generation ({on['Gen Z']:.0%} against {on['Millennials']:.0%} for Millennials); "
             f"Gen X and Millennials make {tx['Millennials']:.0f} transactions a month against {tx['Boomers']:.0f} for Boomers")
    n_z = int(_gen_median(d, "online_share").loc["Gen Z", "n_customers"])
    fig = _style(fig, title, f"Median per customer. Whiskers are 95% bootstrap intervals. Gen Z has only {n_z} customers, "
                 "so its frequency and ticket intervals are wide.", height=400, top=115)
    fig.update_xaxes(tickangle=-30)
    return fig


def birth_year_steps(d: dict) -> go.Figure:
    f = d["features"]
    by = f.groupby("birth_year").agg(share=("late_night_share", "mean"), n=("customer_id", "size")).reset_index()
    cuts = d["artifact"]["birth_year_cuts"]
    fig = go.Figure()
    for x0, x1, label in [(by.birth_year.min() - 1, cuts[0] + 0.5, "Older band"),
                          (cuts[0] + 0.5, cuts[1] + 0.5, "Middle band"),
                          (cuts[1] + 0.5, by.birth_year.max() + 1, "Younger band")]:
        level = f.loc[(f.birth_year > x0) & (f.birth_year <= x1), "late_night_share"].mean() * 100
        fig.add_shape(type="line", x0=x0, x1=x1, y0=level, y1=level, line={"color": ORANGE, "width": 2})
        fig.add_annotation(x=(x0 + x1) / 2, y=1.0, yref="paper", yanchor="bottom", text=f"{label}: {level:.0f}%",
                           showarrow=False, font={"color": INK_2, "size": 12})
    for year, name in [(1945.5, "Boomers"), (1964.5, "Gen X"), (1980.5, "Millennials"), (1996.5, "Gen Z")]:
        fig.add_shape(type="line", x0=year, x1=year, y0=0, y1=1, yref="paper", line={"color": AXIS, "width": 1})
        fig.add_annotation(x=year, y=0.02, yref="paper", text=f"{name} start", showarrow=False, xanchor="left", xshift=3,
                           font={"color": MUTED, "size": 11})
    fig.add_trace(go.Scatter(
        x=by.birth_year, y=by.share * 100, mode="markers", showlegend=False,
        marker={"color": BLUE, "size": 8, "line": {"color": SURFACE, "width": 2}},
        customdata=by.n, hovertemplate="Born %{x}<br>Late-night share %{y:.1f}%<br>%{customdata} customers<extra></extra>",
    ))
    title = (f"Behavior changes in two steps, at birth years {cuts[0]} and {cuts[1]}, "
             f"not at the generation boundaries")
    fig = _style(fig, title, "Mean late-night share of transactions by birth year. Orange lines are the band averages. "
                 "Gray lines are the Pew generation cutoffs.", height=400)
    fig.update_yaxes(ticksuffix="%", range=[19.2, 33], title={"text": "Late-night share", "font": {"color": MUTED, "size": 12}})
    fig.update_xaxes(title={"text": "Birth year", "font": {"color": MUTED, "size": 12}})
    return fig


def effect_sizes(d: dict) -> go.Figure:
    t = d["gen_tests"]
    kw = t[t["test"] == "Kruskal-Wallis"].sort_values("effect_size")
    labels = [config.FEATURE_LABELS.get(m, m) for m in kw["metric"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=labels, x=kw["effect_size"], orientation="h", name="Across the five generations",
                         marker={"color": BLUE, "cornerradius": 3},
                         hovertemplate="%{y}<br>Epsilon squared %{x:.3f}<extra>Across generations</extra>"))
    fig.add_trace(go.Bar(y=labels, x=kw["effect_within_age_band"], orientation="h",
                         name="Between generations inside the same generator age band",
                         marker={"color": ORANGE, "cornerradius": 3},
                         hovertemplate="%{y}<br>Epsilon squared %{x:.3f}<extra>Within age band</extra>"))
    a = d["artifact"]
    title = (f"Inside a generator age band, generation explains almost nothing: median effect "
             f"{a['median_effect_within_age_band']:.3f} against {a['median_effect_by_generation']:.2f} across generations")
    fig = _style(fig, title, "Kruskal-Wallis epsilon squared per metric. 0.01 is small, 0.06 medium, 0.14 large.",
                 height=560, top=135, barmode="group")
    fig.update_layout(bargap=0.3, bargroupgap=0.1)
    fig.update_yaxes(ticksuffix="  ")
    return _horizontal(fig)


# ------------------------------------------------------------------------------ segmentation

def k_selection(d: dict) -> go.Figure:
    k = d["k_table"]
    chosen = d["check"]["chosen_k"]
    row = k[k["k"] == chosen].iloc[0]
    panels = [("silhouette", "Silhouette (higher is better)"),
              ("bootstrap_ari_mean", "Bootstrap ARI (1 = same segments every time)"),
              ("inertia", "Inertia (elbow)")]
    fig = _subplots(rows=1, cols=3, subplot_titles=[p[1] for p in panels], horizontal_spacing=0.08)
    for i, (col, _) in enumerate(panels, start=1):
        fig.add_trace(go.Scatter(x=k["k"], y=k[col], mode="lines+markers", showlegend=False,
                                 line={"color": GRAY, "width": 2},
                                 marker={"color": GRAY, "size": 8, "line": {"color": SURFACE, "width": 2}},
                                 hovertemplate="k = %{x}<br>%{y:.3f}<extra></extra>"), row=1, col=i)
        fig.add_trace(go.Scatter(x=[chosen], y=[row[col]], mode="markers+text", showlegend=False,
                                 text=[f"k = {chosen}"], textposition="top center", textfont={"color": INK, "size": 12},
                                 marker={"color": BLUE, "size": 11, "line": {"color": SURFACE, "width": 2}},
                                 hovertemplate="k = %{x}<br>%{y:.3f}<extra>chosen</extra>"), row=1, col=i)
        fig.update_xaxes(dtick=1, row=1, col=i)
    fig.update_yaxes(range=[0.2, 0.34], row=1, col=1)
    fig.update_yaxes(range=[0.6, 0.99], row=1, col=2)
    title = (f"k = {chosen} has the highest silhouette ({row['silhouette']:.2f}) and stays stable under resampling "
             f"(mean ARI {row['bootstrap_ari_mean']:.2f})")
    return _style(fig, title, "K-means on 16 log-scaled, standardized behavior features, k = 3 to 8. "
                  "ARI compares 100 bootstrap refits with the full-data segments.", height=380, top=125)


def segment_index_heatmap(d: dict) -> go.Figure:
    p = d["profiles"].set_index("segment_name").reindex(SEGMENT_ORDER)
    cols = ["monthly_spend", "monthly_txns", "avg_ticket", *config.SHARE_COLS, "online_share",
            "weekend_share", "late_night_share"]
    portfolio = d["features"][cols].mean()
    index = p[cols] / portfolio
    short = {"monthly_spend": "Monthly spend", "monthly_txns": "Txns per month", "avg_ticket": "Avg ticket",
             "online_share": "Online share", "weekend_share": "Weekend share", "late_night_share": "Late-night share",
             **{f"share_{k}": v for k, v in config.CATEGORY_GROUPS.items()}}
    fig = go.Figure(go.Heatmap(
        z=np.log2(index.to_numpy())[::-1], x=[short[c] for c in cols], y=SEGMENT_ORDER[::-1],
        text=index.to_numpy()[::-1], texttemplate="%{text:.1f}x", textfont={"size": 12},
        colorscale=DIVERGING, zmin=-1.2, zmax=1.2, xgap=2, ygap=2,
        colorbar={"title": {"text": "Index vs average", "side": "right"}, "thickness": 10, "len": 0.8,
                  "tickvals": [-1, 0, 1], "ticktext": ["0.5x", "1.0x", "2.0x"]},
        hovertemplate="%{y}<br>%{x}: %{text:.2f}x the portfolio average<extra></extra>",
    ))
    trav = index.loc["Big-Ticket Travelers", "share_travel"]
    prem = index.loc["Premium Household Shoppers", "monthly_spend"]
    light = index.loc["Light Home and Dining Spenders", "monthly_spend"]
    title = (f"Big-Ticket Travelers put {trav:.1f}x the average share into travel, Premium Household Shoppers "
             f"spend {prem:.1f}x the average, Light Home and Dining Spenders {light:.1f}x")
    fig = _style(fig, title, "Segment mean divided by the portfolio mean. Blue is above average, red is below.",
                 height=370, top=80)
    fig.update_xaxes(tickangle=-35, tickfont={"color": INK_2, "size": 11.5})
    fig.update_yaxes(tickfont={"color": INK_2})
    return fig


def size_vs_spend(d: dict) -> go.Figure:
    p = d["profiles"].set_index("segment_name").reindex(SEGMENT_ORDER[::-1])
    fig = go.Figure()
    for name, row in p.iterrows():
        fig.add_shape(type="line", y0=name, y1=name, x0=row.customer_share * 100, x1=row.spend_share * 100,
                      line={"color": GRAY, "width": 2})
    fig.add_trace(go.Scatter(y=p.index, x=p.customer_share * 100, mode="markers", name="Share of customers",
                             marker={"color": BLUE_RAMP[0], "size": 12, "line": {"color": SURFACE, "width": 2}},
                             hovertemplate="%{y}<br>%{x:.1f}% of customers<extra></extra>"))
    fig.add_trace(go.Scatter(y=p.index, x=p.spend_share * 100, mode="markers+text", name="Share of spend",
                             text=[f"{v:.0%}" for v in p.spend_share],
                             textposition=["middle right" if s >= c else "middle left"
                                           for s, c in zip(p.spend_share, p.customer_share)],
                             textfont={"color": INK_2, "size": 12},
                             marker={"color": BLUE_RAMP[3], "size": 12, "line": {"color": SURFACE, "width": 2}},
                             hovertemplate="%{y}<br>%{x:.1f}% of spend<extra></extra>"))
    top = p.loc["Premium Household Shoppers"]
    low = p.loc["Light Home and Dining Spenders"]
    title = (f"Premium Household Shoppers are {top.customer_share:.0%} of customers and {top.spend_share:.0%} of spend; "
             f"Light Home and Dining Spenders are {low.customer_share:.0%} and {low.spend_share:.0%}")
    fig = _style(fig, title, "Each segment's share of customers and of total spend", height=360, top=125)
    fig.update_xaxes(ticksuffix="%", range=[0, 55])
    return _horizontal(fig)


def generation_mix(d: dict) -> go.Figure:
    p = d["profiles"].set_index("segment_name").reindex(SEGMENT_ORDER[::-1])
    fig = go.Figure()
    for gen, color in zip(config.GENERATIONS, BLUE_RAMP):
        vals = p[f"gen_{gen}"] * 100
        fig.add_trace(go.Bar(
            y=p.index, x=vals, orientation="h", name=gen,
            marker={"color": color, "line": {"color": SURFACE, "width": 2}},
            text=[f"{v:.0f}%" if v >= 9 else "" for v in vals], textposition="inside", insidetextanchor="middle",
            textfont={"color": "white" if color in BLUE_RAMP[2:] else INK, "size": 12},
            hovertemplate="%{y}<br>" + gen + ": %{x:.0f}%<extra></extra>",
        ))
    dig = p.loc["Digital Shoppers", "gen_Gen Z"]
    light = p.loc["Light Home and Dining Spenders"]
    older = light["gen_Silent"] + light["gen_Boomers"]
    title = (f"Digital Shoppers are {dig:.0%} Gen Z and Light Home and Dining Spenders are {older:.0%} Boomers or Silent, "
             f"although age was never an input")
    fig = _style(fig, title, "Generation mix inside each behavior segment", height=380, top=135, barmode="stack")
    fig.update_layout(bargap=0.4, legend={"traceorder": "normal"})
    fig.update_xaxes(ticksuffix="%", range=[0, 100])
    return _horizontal(fig)


def generator_check(d: dict) -> go.Figure:
    c = d["check"]
    labels = {"inferred_age_band": "Generator age band (inferred)", "generation": "Generation",
              "gender": "Gender", "city_size_band": "City size band",
              "transactions_per_day_tier": "Transactions-per-day tier"}
    v = pd.Series(c["cramers_v"]).rename(labels).sort_values()
    fig = go.Figure(go.Bar(y=v.index, x=v.values, orientation="h", marker={"color": BLUE, "cornerradius": 4},
                           text=[f"{x:.2f}" for x in v.values], textposition="outside",
                           textfont={"color": INK_2}, cliponaxis=False,
                           hovertemplate="%{y}<br>Cramer's V with segment: %{x:.2f}<extra></extra>"))
    title = (f"Birth year, gender and city size alone predict the behavior segment for "
             f"{c['demographics_only_accuracy']:.0%} of customers (always guessing the largest segment gets "
             f"{c['majority_baseline_accuracy']:.0%})")
    fig = _style(fig, title, "Cramer's V between segment and each generator bucket. 0 is no association, 1 is perfect.",
                 height=340, top=125)
    fig.update_xaxes(range=[0, 1])
    return _horizontal(fig)


# ------------------------------------------------------------------------------ targeting

def targeting_scores(d: dict) -> go.Figure:
    t = d["targeting"]
    benefits = list(t["benefit"].unique())
    labels = [t[t.benefit == b]["benefit_label"].iloc[0] for b in benefits]
    fig = _subplots(rows=1, cols=2, subplot_titles=labels, horizontal_spacing=0.3)
    for i, b in enumerate(benefits, start=1):
        sub = t[t.benefit == b].sort_values("score")
        fig.add_trace(go.Bar(
            y=sub.segment_name, x=sub.score, orientation="h", showlegend=False,
            marker={"color": BLUE, "cornerradius": 4},
            text=[f"{s:.2f}" for s in sub.score], textposition="outside", textfont={"color": INK_2}, cliponaxis=False,
            customdata=np.stack([sub.engagement, sub.headroom, sub.value, sub.n_customers], axis=1),
            hovertemplate="%{y}<br>Score %{x:.2f}<br>Engagement %{customdata[0]:.2f} x headroom %{customdata[1]:.2f} "
                          "x value %{customdata[2]:.2f}<br>%{customdata[3]} customers<extra></extra>",
        ), row=1, col=i)
        fig.update_xaxes(range=[0, 0.62], row=1, col=i)
    top = {b: t[(t.benefit == b) & (t["rank"] == 1)].iloc[0] for b in benefits}
    last_travel = t[(t.benefit == "travel_credit")].sort_values("rank").iloc[-1]
    if top["dining_credit"].segment_name == top["travel_credit"].segment_name:
        lead = f"{top['dining_credit'].segment_name} rank first for both credits"
    else:
        lead = (f"{top['dining_credit'].segment_name} rank first for the dining credit and "
                f"{top['travel_credit'].segment_name} for the travel credit")
    title = (f"{lead}; {last_travel.segment_name} rank last for the travel credit because the score sees "
             f"no headroom ({last_travel.headroom:.2f})")
    fig = _style(fig, title, "Score = engagement x headroom x value. Hover for the three parts.", height=380, top=135)
    return _horizontal(fig)


# ------------------------------------------------------------------------------ triggers

def trigger_monthly(d: dict) -> go.Figure:
    m = d["trig_monthly"]
    fig = _subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12,
                        subplot_titles=["Customers firing per month", "Spend at stake per month ($)"])
    for trig in TRIGGERS:
        sub = m[m.trigger_name == trig]
        for row, col, fmt in [(1, "customers_firing", "%{y} customers"), (2, "spend_at_stake", "$%{y:,.0f}")]:
            fig.add_trace(go.Scatter(
                x=sub.month, y=sub[col], mode="lines", name=TRIGGER_LABELS[trig], legendgroup=trig,
                showlegend=row == 1, line={"color": TRIGGER_COLORS[trig], "width": 2},
                hovertemplate=f"{TRIGGER_LABELS[trig]}<br>%{{x|%b %Y}}<br>{fmt}<extra></extra>",
            ), row=row, col=1)
    live = m[m.customers_firing > 0]
    med = live.groupby("trigger_name")["customers_firing"].median()
    s = d["trig_summary"].set_index("trigger_name")
    title = (f"Travel drop reaches about {med['travel_drop']:.0f} customers a month and dining cooling about "
             f"{med['dining_cooling']:.0f}; first travel fired {int(s.loc['first_travel', 'fires'])} times in two years")
    fig = _style(fig, title, "Monthly backtest on 2019 and 2020. The first travel-drop month is high because every "
                 "customer already in a drop fires at once when scoring starts.", height=540, top=120)
    fig.update_layout(hovermode="x unified", legend={"y": -0.08, "yanchor": "top"})
    fig.update_yaxes(rangemode="tozero")
    fig.update_yaxes(tickprefix="$", row=2, col=1)
    return fig


def seasonality_adjustment(d: dict) -> go.Figure:
    a = d["trig_monthly"].query("trigger_name == 'dining_cooling'")
    u = d["trig_unadjusted"].query("trigger_name == 'dining_cooling'")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=u.month, y=u.customers_firing, mode="lines", name="Measured against own past only",
                             line={"color": GRAY, "width": 2},
                             hovertemplate="%{x|%b %Y}<br>%{y} customers<extra>Unadjusted</extra>"))
    fig.add_trace(go.Scatter(x=a.month, y=a.customers_firing, mode="lines", name="Measured relative to the portfolio",
                             line={"color": BLUE, "width": 2},
                             hovertemplate="%{x|%b %Y}<br>%{y} customers<extra>Portfolio-adjusted</extra>"))
    peak = u.loc[u.customers_firing.idxmax()]
    fig.add_annotation(x=peak.month, y=peak.customers_firing, text=f"{int(peak.customers_firing)} customers",
                       showarrow=False, xanchor="left", xshift=8, font={"color": INK_2, "size": 12})
    title = (f"Without the portfolio adjustment, dining cooling fires for {int(peak.customers_firing)} customers in "
             f"{peak.month:%B %Y}; with it, the busiest month has {int(a.customers_firing.max())}")
    fig = _style(fig, title, "Customers firing the dining cooling trigger per month, same thresholds, with and "
                 "without the adjustment for shared seasonality", height=380, top=135)
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(rangemode="tozero")
    return fig


def placebo(d: dict) -> go.Figure:
    p = d["trig_placebo"]
    x = [TRIGGER_LABELS[t] for t in p.trigger_name]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=p.actual_fires, name="Real month order", marker={"color": BLUE, "cornerradius": 4},
                         text=[f"{v:,.0f}" for v in p.actual_fires], textposition="outside", textfont={"color": INK_2},
                         hovertemplate="%{x}<br>%{y:,.0f} fires on real data<extra></extra>"))
    fig.add_trace(go.Bar(
        x=x, y=p.placebo_fires_mean, name="Months shuffled within each customer (mean of 20 runs)",
        marker={"color": GRAY, "cornerradius": 4},
        text=[f"{v:,.0f}" for v in p.placebo_fires_mean], textposition="outside", textfont={"color": INK_2},
        customdata=np.stack([p.placebo_fires_min, p.placebo_fires_max], axis=1),
        hovertemplate="%{x}<br>%{y:,.0f} fires on shuffled data<br>range %{customdata[0]} to %{customdata[1]}<extra></extra>",
    ))
    r = p.set_index("trigger_name")["actual_to_placebo_ratio"]
    title = (f"Both drop triggers fire about as often on shuffled months as on real ones "
             f"({r['travel_drop']:.2f}x and {r['dining_cooling']:.2f}x), so in this data they catch noise")
    fig = _style(fig, title, "Seasonality removed, then each customer's months put in random order. A trigger that "
                 "detects real sustained change should fire more on the real order.", height=400, top=150,
                 barmode="group")
    fig.update_layout(bargap=0.72, bargroupgap=0.12)
    fig.update_yaxes(range=[0, p.placebo_fires_max.max() * 1.18])
    return fig


def follow_up(d: dict) -> go.Figure:
    f = d["trig_follow_up"].query("scope == 'All customers'").set_index("trigger_name")
    stages = ["Baseline<br>window", "Trigger<br>window", "Months after<br>firing", "Long-run<br>average"]
    cols = ["baseline_index", "trigger_period_index", "follow_up_index", "long_run_index"]
    names = {"travel_drop": "Travel drop (travel spend)", "dining_cooling": "Dining cooling (dining transactions)"}
    fig = _subplots(rows=1, cols=2, subplot_titles=[names[t] for t in names], horizontal_spacing=0.1)
    for i, trig in enumerate(names, start=1):
        vals = f.loc[trig, cols].astype(float).to_numpy()
        fig.add_trace(go.Bar(x=stages, y=vals, showlegend=False,
                             marker={"color": [BLUE, BLUE, BLUE, GRAY], "cornerradius": 4},
                             text=[f"{v:.2f}" for v in vals], textposition="outside", textfont={"color": INK_2},
                             hovertemplate="%{x}<br>Index %{y:.2f} (baseline = 1)<extra></extra>"), row=1, col=i)
        fig.update_yaxes(range=[0, 1.18], row=1, col=i)
    t = f.loc["travel_drop"]
    title = (f"After a trigger fires, customers return to their usual level with no offer: travel spend goes from "
             f"{t.trigger_period_index:.2f} to {t.follow_up_index:.2f} of baseline, and their long-run average is "
             f"{t.long_run_index:.2f}")
    fig = _style(fig, title, "Seasonality-adjusted, summed over fired events, indexed to the baseline window. "
                 "The baseline was an unusually high period, so the 'drop' is mostly a return to normal.",
                 height=420, top=140)
    fig.update_xaxes(tickangle=0)
    fig.update_layout(bargap=0.6)
    return fig


FIGURES = {
    "wallet_heatmap": wallet_heatmap,
    "generation_bars": generation_bars,
    "birth_year_steps": birth_year_steps,
    "effect_sizes": effect_sizes,
    "k_selection": k_selection,
    "segment_index_heatmap": segment_index_heatmap,
    "size_vs_spend": size_vs_spend,
    "generation_mix": generation_mix,
    "generator_check": generator_check,
    "targeting_scores": targeting_scores,
    "trigger_monthly": trigger_monthly,
    "seasonality_adjustment": seasonality_adjustment,
    "placebo": placebo,
    "follow_up": follow_up,
}


def build_all(d: dict) -> dict[str, go.Figure]:
    return {name: fn(d) for name, fn in FIGURES.items()}
