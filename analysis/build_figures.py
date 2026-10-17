"""Write the four figures embedded in docs/FINDINGS.md.

Figures use the same comparison as cereal_extra_units.py and cereal_story.py.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cereal_extra_units import (  # noqa: E402
    MARGINS,
    breakeven_margin,
    eligible_products,
    margin_change,
    product_weeks,
)
from cereal_story import (  # noqa: E402
    HOUSEHOLD_LABELS,
    KIDS_COMPOSITION,
    campaign_cereal_change,
    comparison_frame,
    segment_table,
)

OUT = Path(__file__).resolve().parents[1] / "docs" / "figures"
INK = "#1c1c1c"
MUTED = "#5c6570"
NEGATIVE = "#9a4a3a"
POSITIVE = "#1f6b4a"
BAR = "#24537a"
COMPARE = "#8a939c"
GRID = "#e6e8eb"


def apply_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.titleweight": "medium",
            "axes.labelsize": 11,
            "axes.edgecolor": "#c5c9ce",
            "text.color": INK,
            "axes.labelcolor": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def finish(ax: plt.Axes, path: Path, horizontal_grid: bool) -> None:
    ax.grid(axis="x" if horizontal_grid else "y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    path.parent.mkdir(parents=True, exist_ok=True)
    ax.figure.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(ax.figure)


def margin_figure(products) -> None:
    changes = [margin_change(products, margin) for margin in MARGINS]
    labels = [f"{margin:.0%}" for margin in MARGINS]
    colors = [NEGATIVE if value < 0 else POSITIVE for value in changes]
    fig, ax = plt.subplots(figsize=(8, 4.6), layout="constrained")
    bars = ax.bar(labels, changes, color=colors, width=0.72)
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.bar_label(bars, labels=[f"${value:,.0f}" for value in changes], padding=4, fontsize=10, color=INK)
    ax.set_title("Change in margin dollars during discount weeks")
    ax.set_xlabel("Assumed gross margin")
    ax.set_ylabel("Change versus the full-price pace (dollars)")
    low = min(changes)
    high = max(changes)
    ax.set_ylim(low * 1.18, high * 1.35)
    finish(ax, OUT / "margin-dollars.png", horizontal_grid=False)


def household_figure(table) -> None:
    ordered = table.sort_values("extra_units", ascending=True)
    labels = [HOUSEHOLD_LABELS.get(value, value) for value in ordered["segment"]]
    values = ordered["extra_units"].to_numpy()
    fig, ax = plt.subplots(figsize=(8, 5.2), layout="constrained")
    bars = ax.barh(labels, values, color=BAR, height=0.68)
    ax.bar_label(bars, labels=[f"{value:,.0f}" for value in values], padding=4, fontsize=10, color=INK)
    ax.set_title("Extra boxes by household type")
    ax.set_xlabel("Extra boxes during discount weeks")
    ax.set_xlim(0, values.max() * 1.16)
    finish(ax, OUT / "extra-boxes-by-household.png", horizontal_grid=True)


def children_figure(table) -> None:
    order = ["1", "2", "3+"]
    ordered = table.set_index("segment").loc[order]
    labels = ["1 child", "2 children", "3 or more"]
    values = ordered["lift"].to_numpy() * 100
    fig, ax = plt.subplots(figsize=(7.2, 4.4), layout="constrained")
    bars = ax.bar(labels, values, color=BAR, width=0.68)
    ax.bar_label(bars, labels=[f"{value:.0f}%" for value in values], padding=4, fontsize=10, color=INK)
    ax.set_title("Lift by number of children")
    ax.set_xlabel("Children in the household")
    ax.set_ylabel("Lift (percent)")
    ax.set_ylim(0, values.max() * 1.2)
    finish(ax, OUT / "lift-by-children.png", horizontal_grid=False)


def campaign_figure(table) -> None:
    labels = [value.replace("Type", "Type ") for value in table["campaign_type"]]
    mailed = table["recipient_change"].to_numpy() * 100
    unmatched = table["control_change"].to_numpy() * 100
    x = np.arange(len(labels))
    width = 0.36
    fig, ax = plt.subplots(figsize=(8, 4.6), layout="constrained")
    mailed_bars = ax.bar(x - width / 2, mailed, width, label="Households mailed", color=BAR)
    other_bars = ax.bar(x + width / 2, unmatched, width, label="Households not mailed", color=COMPARE)
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.bar_label(mailed_bars, labels=[f"{value:+.1f}%" for value in mailed], padding=3, fontsize=9, color=INK)
    ax.bar_label(other_bars, labels=[f"{value:+.1f}%" for value in unmatched], padding=3, fontsize=9, color=INK)
    ax.set_xticks(x, labels)
    ax.set_title("Change in cereal units per day during campaigns")
    ax.set_xlabel("Campaign type")
    ax.set_ylabel("Change from the preceding window of the same length")
    span = max(np.max(np.abs(mailed)), np.max(np.abs(unmatched)))
    ax.set_ylim(-span * 1.7, span * 1.7)
    ax.legend(frameon=False, loc="upper right")
    finish(ax, OUT / "campaign-cereal-change.png", horizontal_grid=False)


def main() -> None:
    apply_style()
    weeks = product_weeks()
    products = eligible_products(weeks)
    lines, week_counts = comparison_frame(products, weeks)
    margin_figure(products)
    household_figure(segment_table(lines, week_counts, "household_type"))
    kids = lines[lines["household_type"].isin(KIDS_COMPOSITION)]
    children_figure(segment_table(kids, week_counts, "KID_CATEGORY_DESC"))
    campaign_figure(campaign_cereal_change())
    print(f"Margin required: {breakeven_margin(products):.1%}")
    print(f"Wrote figures to {OUT}")


if __name__ == "__main__":
    main()
