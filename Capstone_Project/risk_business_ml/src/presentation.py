"""Portable figures shared by the executed notebook and result preview."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
import pandas as pd

from analyze import RISK_FEATURES, RISK_LABELS, TARGET_LABELS

ROOT = Path(__file__).resolve().parents[1]
BLUE, GOLD, GRAY = "#225d8d", "#b07832", "#495563"
SHORT = {"revenue_growth_pct": "Revenue growth", "operating_margin_change_pp": "Operating margin change",
         "net_margin_change_pp": "Net margin change", "daily_notional_growth_pct": "Daily notional growth",
         "daily_sides_growth_pct": "Daily sides growth"}


def style():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.titlesize": 14,
                         "axes.labelsize": 11, "figure.facecolor": "white", "axes.facecolor": "white",
                         "axes.spines.top": False, "axes.spines.right": False,
                         "grid.color": "#e6e8ec", "grid.linewidth": 0.7})


def save(fig, name):
    destination = ROOT / "results/figures"
    destination.mkdir(exist_ok=True)
    fig.savefig(destination / f"{name}.png", dpi=160, bbox_inches="tight", facecolor="white")
    return fig


def correlation_heatmap(associations):
    style()
    order = [(e, m) for e in ["FICC", "NSCC", "DTC", "FICC/GSD", "FICC/MBSD"]
             for m in SHORT if ((associations.entity == e) & (associations.metric == m)).any()]
    matrix = associations.pivot(index=["entity", "metric"], columns="risk_feature", values="spearman_rho").reindex(order)[RISK_FEATURES]
    n = associations.groupby(["entity", "metric"]).n_quarters.first()
    cmap = LinearSegmentedColormap.from_list("signed", [GOLD, "#fafafa", BLUE])
    fig, ax = plt.subplots(figsize=(14, 9), layout="constrained")
    im = ax.imshow(matrix.values, cmap=cmap, vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(6), ["Market volatility\nchange", "Treasury yield\nrepricing", "Credit conditions\nchange",
                            "Funding basis\npressure", "Fed regulatory\ncommunication", "Fed monetary\ncommunication"])
    ax.tick_params(axis="x", bottom=False, labeltop=True, labelbottom=False, pad=10)
    ax.set_yticks(range(len(order)), [f"{e}  {SHORT[m]}  (n={n.loc[e, m]})" for e, m in order])
    for i in range(len(order)):
        for j in range(6):
            value = matrix.iloc[i, j]
            ax.text(j, i, f"{value:+.2f}", ha="center", va="center", color="#142330", fontsize=11)
    ax.set_title("Risk proxies and business changes: same-quarter Spearman correlations", pad=56)
    colorbar = fig.colorbar(im, ax=ax, shrink=.8, pad=.025)
    colorbar.set_label("Spearman rho (unitless)")
    fig.supxlabel("2020Q1–2026Q2 financial changes; 2021Q1–2026Q2 FICC activity changes.\nMissing quarters excluded. None of 78 comparisons passes exploratory FDR 5%.", fontsize=10)
    return save(fig, "association_heatmap")


def association_uncertainty(associations):
    style()
    strongest = associations.sort_values("abs_spearman", ascending=False).head(6).iloc[::-1]
    fig, ax = plt.subplots(figsize=(13, 6), layout="constrained")
    positions = np.arange(len(strongest))
    for i, (_, row) in enumerate(strongest.iterrows()):
        ax.plot([row.pearson_block_bootstrap_ci_low, row.pearson_block_bootstrap_ci_high], [i, i], color=GRAY, lw=2)
        ax.plot(row.pearson_r, i, "o", color=BLUE, ms=8)
        ax.plot(row.spearman_rho, i, "D", mfc="white", mec=GOLD, ms=7)
    labels = [f"{r.entity} {SHORT[r.metric]}\n{RISK_LABELS[r.risk_feature]} (n={r.n_quarters})" for _, r in strongest.iterrows()]
    ax.set_yticks(positions, labels)
    ax.axvline(0, color="#6b7280", lw=1)
    ax.set_xlim(-1.03, 1.03)
    ax.set_xlabel("Correlation (unitless)")
    ax.set_title("Leading descriptive associations and their uncertainty", pad=64)
    ax.plot([], [], "o", color=BLUE, label="Pearson r with 95% paired block-bootstrap interval")
    ax.plot([], [], "D", mfc="white", mec=GOLD, label="Spearman rho; interval shown is for Pearson only")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), frameon=False, fontsize=9)
    ax.grid(axis="x")
    fig.supxlabel("Exploratory selection from 78 comparisons. Intervals are not adjusted for selection or multiple testing.\n4-quarter circular moving blocks, 2,000 resamples. No causal interpretation.", fontsize=10)
    return save(fig, "association_uncertainty")


def model_comparison(metrics):
    style()
    d = metrics[metrics.model == "controls_plus_risks"].copy()
    d = d.sort_values("mae_improvement_vs_controls_pct")
    fig, ax = plt.subplots(figsize=(12, 8), layout="constrained")
    value = d.mae_improvement_vs_controls_pct
    ax.barh(np.arange(len(d)), value, color=[BLUE if v > 0 else GOLD for v in value], height=.65)
    ax.set_yticks(range(len(d)), [f"{r.entity} {SHORT[r.metric]} (test n={r.test_n})" for _, r in d.iterrows()])
    for i, v in enumerate(value):
        ax.text(v + (1 if v >= 0 else -1), i, f"{v:+.1f}%", ha="left" if v >= 0 else "right", va="center", fontsize=10)
    ax.axvline(0, color=GRAY, lw=1)
    ax.set_xlim(min(-65, value.min() - 13), max(24, value.max() + 10))
    ax.set_xlabel("Reduction in test MAE after adding risk proxies (%)")
    ax.set_title("Do risk proxies improve the retrospective holdout mapping?")
    ax.grid(axis="x")
    fig.supxlabel("2025Q3–2026Q2 calendar holdout; NSCC has only 2 usable quarters. Positive = smaller error.\nControls: prior business change and quarter of year. These tiny holdouts do not establish general usefulness.", fontsize=10)
    return save(fig, "holdout_model_comparison")


def ficc_holdout(predictions):
    style()
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.5))
    fig.subplots_adjust(top=.76, bottom=.20, left=.065, right=.985, wspace=.30)
    quarters = ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]
    for ax, metric in zip(axes, ["revenue_growth_pct", "operating_margin_change_pp", "net_margin_change_pp"]):
        d = predictions[(predictions.entity == "FICC") & (predictions.metric == metric)]
        table = d.pivot(index="quarter", columns="model", values="predicted").reindex(quarters)
        actual = d.groupby("quarter").actual.first().reindex(quarters)
        x = np.arange(4)
        ax.scatter(x - .18, actual, marker="o", color="#26303b", s=48, label="Actual")
        ax.scatter(x, table.controls_only, marker="s", facecolors="white", edgecolors=GOLD, s=48, label="Controls only")
        ax.scatter(x + .18, table.controls_plus_risks, marker="D", color=BLUE, s=42, label="Controls + risks")
        ax.axhline(0, lw=.8, color="#737f8c")
        ax.set_xticks(x, quarters)
        ax.set_ylabel("Percent QoQ" if metric.endswith("pct") else "Percentage points")
        ax.set_title(SHORT[metric], fontsize=13)
        ax.grid(axis="y")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(.5, .91))
    fig.suptitle("FICC: actual business changes and same-quarter model estimates", y=.98, fontsize=15)
    fig.supxlabel("4 held-out quarters. Current-vintage risk data; not a verified real-time forecast. Each panel has its own unit and scale.", fontsize=10, y=.025)
    return save(fig, "ficc_holdout")


def source_coverage(financial):
    style()
    fig, ax = plt.subplots(figsize=(12, 4.6), layout="constrained")
    quarters = pd.period_range("2020Q1", "2026Q2", freq="Q")
    for e, color, marker in [("FICC", BLUE, "o"), ("NSCC", GOLD, "s"), ("DTC", GRAY, "^")]:
        d = financial[financial.entity == e].set_index("quarter").reindex(quarters.astype(str))
        ax.plot(np.arange(len(quarters)), d.revenue_usd / 1e6, color=color, marker=marker, ms=4, lw=1.5, label=e)
    ticks = [0, 4, 8, 12, 16, 20, len(quarters) - 1]
    ax.set_xticks(ticks, quarters[ticks].astype(str))
    ax.set_ylabel("Quarterly revenue (USD millions)")
    ax.set_title("Business data coverage; missing quarters break the lines")
    ax.legend(ncol=3, frameon=False, loc="upper left")
    ax.set_ylim(bottom=0)
    ax.grid(axis="y")
    fig.supxlabel("Source: legal-entity financial statements. NSCC and DTC totals include activities outside ECS.", fontsize=10)
    return save(fig, "business_coverage")


def scatter_examples(panel):
    style()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
    for ax, (entity, metric, feature) in zip(axes, [
        ("FICC/GSD", "daily_sides_growth_pct", "vix_change_pct"),
        ("FICC", "revenue_growth_pct", "funding_basis_max_bps")]):
        d = panel[(panel.entity == entity) & (panel.metric == metric)].dropna(subset=["target", feature])
        ax.scatter(d[feature], d.target, color=BLUE, s=42, alpha=.8)
        for _, row in d.iterrows():
            if abs(row.target) == abs(d.target).max() or row[feature] == d[feature].max():
                ax.annotate(row.quarter, (row[feature], row.target), xytext=(4, 6), textcoords="offset points", fontsize=9)
        ax.axhline(0, color=GRAY, lw=.8)
        ax.set_xlabel("Quarterly VIX mean change (%)" if feature == "vix_change_pct" else "Quarterly max SOFR − EFFR (basis points)")
        ax.set_ylabel(TARGET_LABELS[metric])
        ax.set_title(f"{entity}: {SHORT[metric]} (n={len(d)})", fontsize=13)
        ax.grid(alpha=.8)
    fig.supxlabel("Each point is one quarter. Higher activity or revenue is not evidence of lower clearing risk.\nA funding basis is a market proxy, not FICC's own liquidity shortfall.", fontsize=10)
    return save(fig, "association_scatter")
