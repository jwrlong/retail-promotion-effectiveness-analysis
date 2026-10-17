"""Break the cold-cereal discount result down along the story.

The comparison is the same one used in cereal_extra_units.py. A product-week
is on discount when at least 80% of boxes had a retail price cut, and full
price when 20% or fewer did. Extra boxes are discount-week sales above that
cereal's own full-price weekly pace.

Household type and number of children describe who bought those extra boxes.
Only the surveyed households have those fields. Cereal type and brand use
every household. The campaign section is a different promotion: mailed
campaigns, not the shelf price cut. It asks whether households with children
bought more cereal during a mailing than in the same number of days before it.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cereal_extra_units import (  # noqa: E402
    DATA,
    breakeven_margin,
    eligible_products,
    margin_change,
    product_weeks,
)

KIDS_COMPOSITION = ("1 Adult Kids", "2 Adults Kids")
HOUSEHOLD_LABELS = {
    "1 Adult Kids": "One adult with children",
    "2 Adults Kids": "Two adults with children",
    "2 Adults No Kids": "Two adults, no children",
    "Single Female": "Single woman",
    "Single Male": "Single man",
    "Unknown": "Surveyed, type unknown",
    "Not surveyed": "Not surveyed",
}


def comparison_frame(products: pd.DataFrame, weeks: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    eligible_ids = set(products["PRODUCT_ID"])
    state = weeks[weeks["PRODUCT_ID"].isin(eligible_ids) & weeks["state"].isin(["on", "off"])]
    state = state[["PRODUCT_ID", "WEEK_NO", "state"]]
    week_counts = state.groupby(["PRODUCT_ID", "state"]).size().unstack()
    transactions = pd.read_parquet(
        DATA / "fact_transactions.parquet",
        columns=["household_key", "PRODUCT_ID", "DAY", "WEEK_NO", "QUANTITY", "SALES_VALUE"],
    )
    households = pd.read_parquet(
        DATA / "dim_household.parquet",
        columns=["household_key", "HH_COMP_DESC", "KID_CATEGORY_DESC", "HasDemographics"],
    )
    lines = transactions[transactions["PRODUCT_ID"].isin(eligible_ids)]
    lines = lines.merge(state, on=["PRODUCT_ID", "WEEK_NO"], how="inner")
    lines = lines.merge(households, on="household_key", how="left")
    lines["household_type"] = np.where(
        lines["HasDemographics"].fillna(False),
        lines["HH_COMP_DESC"],
        "Not surveyed",
    )
    lines = lines.merge(
        products[["PRODUCT_ID", "SUB_COMMODITY_DESC", "BRAND", "full_price"]],
        on="PRODUCT_ID",
        how="left",
    )
    return lines, week_counts


def segment_table(lines: pd.DataFrame, week_counts: pd.DataFrame, column: str) -> pd.DataFrame:
    grouped = lines.groupby(["PRODUCT_ID", "state", column], as_index=False).agg(
        units=("QUANTITY", "sum"),
        paid=("SALES_VALUE", "sum"),
    )
    rows = []
    for segment, sub in grouped.groupby(column):
        units = sub.pivot(index="PRODUCT_ID", columns="state", values="units").reindex(week_counts.index).fillna(0)
        paid = sub.pivot(index="PRODUCT_ID", columns="state", values="paid").reindex(week_counts.index).fillna(0)
        for side in ("on", "off"):
            if side not in units.columns:
                units[side] = 0
            if side not in paid.columns:
                paid[side] = 0
        full_price = lines.drop_duplicates("PRODUCT_ID").set_index("PRODUCT_ID")["full_price"]
        full_price = full_price.reindex(week_counts.index)
        product = pd.DataFrame(
            {
                "baseline_units": (units["off"] / week_counts["off"]) * week_counts["on"],
                "units_on": units["on"],
                "full_price": full_price.to_numpy(),
            }
        )
        product["price_paid_on_discount"] = np.where(
            product["units_on"].gt(0),
            paid["on"] / product["units_on"],
            product["full_price"],
        )
        product = product[(product["baseline_units"] > 0) | (product["units_on"] > 0)]
        extra = float((product["units_on"] - product["baseline_units"]).sum())
        baseline = float(product["baseline_units"].sum())
        rows.append(
            {
                "segment": segment,
                "households": int(lines.loc[lines[column].eq(segment), "household_key"].nunique()),
                "discount_units": float(product["units_on"].sum()),
                "baseline_units": baseline,
                "extra_units": extra,
                "lift": extra / baseline if baseline else np.nan,
                "margin_needed": breakeven_margin(product) if extra > 0 else np.nan,
                "change_at_35": margin_change(product, 0.35),
            }
        )
    table = pd.DataFrame(rows).sort_values("extra_units", ascending=False)
    return table


def campaign_cereal_change() -> pd.DataFrame:
    """Cereal boxes per day during a mailing versus the same number of days before it."""
    campaigns = pd.read_parquet(DATA / "dim_campaign.parquet")
    received = pd.read_parquet(DATA / "fact_campaign_received.parquet").merge(campaigns, on="CAMPAIGN")
    households = pd.read_parquet(
        DATA / "dim_household.parquet",
        columns=["household_key", "HH_COMP_DESC"],
    )
    kids = set(households.loc[households["HH_COMP_DESC"].isin(KIDS_COMPOSITION), "household_key"])
    received = received[received["household_key"].isin(kids)]

    products = pd.read_parquet(DATA / "dim_product.parquet", columns=["PRODUCT_ID", "COMMODITY_DESC"])
    cereal_ids = set(products.loc[products["COMMODITY_DESC"].eq("COLD CEREAL"), "PRODUCT_ID"])
    purchases = pd.read_parquet(
        DATA / "fact_transactions.parquet",
        columns=["household_key", "PRODUCT_ID", "DAY", "QUANTITY"],
    )
    purchases = purchases[purchases["PRODUCT_ID"].isin(cereal_ids) & purchases["household_key"].isin(kids)]
    by_household = {key: group for key, group in purchases.groupby("household_key")}

    def units_in_window(household_key: int, start: int, end: int) -> tuple[float, int]:
        end = min(int(end), 711)
        start = int(start)
        length = end - start + 1
        if length <= 0:
            return 0.0, 0
        household_days = by_household.get(household_key)
        if household_days is None:
            return 0.0, length
        window = household_days[(household_days["DAY"] >= start) & (household_days["DAY"] <= end)]
        return float(window["QUANTITY"].sum()), length

    rows = []
    for campaign_type, mailed in received.groupby("CAMPAIGN_TYPE"):
        pre_units = pre_days = post_units = post_days = 0.0
        kept = 0
        for mailing in mailed.itertuples(index=False):
            duration = int(mailing.END_DAY) - int(mailing.START_DAY) + 1
            pre_start = int(mailing.START_DAY) - duration
            if pre_start < 1:
                continue
            pre_u, pre_d = units_in_window(mailing.household_key, pre_start, int(mailing.START_DAY) - 1)
            post_u, post_d = units_in_window(mailing.household_key, mailing.START_DAY, mailing.END_DAY)
            pre_units += pre_u
            pre_days += pre_d
            post_units += post_u
            post_days += post_d
            kept += 1
        recipients = set(mailed["household_key"])
        control_households = kids - recipients
        control_pre_u = control_pre_d = control_post_u = control_post_d = 0.0
        type_campaigns = campaigns[campaigns["CAMPAIGN_TYPE"].eq(campaign_type)]
        for mailing in type_campaigns.itertuples(index=False):
            duration = int(mailing.END_DAY) - int(mailing.START_DAY) + 1
            pre_start = int(mailing.START_DAY) - duration
            if pre_start < 1:
                continue
            for household_key in control_households:
                pre_u, pre_d = units_in_window(household_key, pre_start, int(mailing.START_DAY) - 1)
                post_u, post_d = units_in_window(household_key, mailing.START_DAY, mailing.END_DAY)
                control_pre_u += pre_u
                control_pre_d += pre_d
                control_post_u += post_u
                control_post_d += post_d
        recipient_change = (post_units / post_days) / (pre_units / pre_days) - 1
        control_change = (control_post_u / control_post_d) / (control_pre_u / control_pre_d) - 1
        rows.append(
            {
                "campaign_type": campaign_type,
                "recipient_households": mailed["household_key"].nunique(),
                "mailings": kept,
                "recipient_change": recipient_change,
                "control_households": len(control_households),
                "control_change": control_change,
            }
        )
    return pd.DataFrame(rows).sort_values("campaign_type")


def print_table(title: str, table: pd.DataFrame) -> None:
    print(f"\n{title}")
    show = table.copy()
    if "segment" in show.columns:
        show["segment"] = show["segment"].map(lambda value: HOUSEHOLD_LABELS.get(value, value))
    print(show.to_string(index=False))


def main() -> None:
    weeks = product_weeks()
    products = eligible_products(weeks)
    lines, week_counts = comparison_frame(products, weeks)
    extra = products["extra_units"].sum()
    baseline = products["baseline_units"].sum()
    print(f"Extra boxes: {extra:,.0f}")
    print(f"Lift: {extra / baseline:.1%}")
    print(f"Margin needed: {breakeven_margin(products):.1%}")

    by_household = segment_table(lines, week_counts, "household_type")
    print_table("Household type", by_household)

    kids = lines[lines["household_type"].isin(KIDS_COMPOSITION)]
    by_children = segment_table(kids, week_counts, "KID_CATEGORY_DESC")
    print_table("Children in households with children", by_children)

    print_table("Cereal type", segment_table(lines, week_counts, "SUB_COMMODITY_DESC"))
    print_table("Brand", segment_table(lines, week_counts, "BRAND"))
    print("\nCampaigns, households with children")
    print(campaign_cereal_change().to_string(index=False))


if __name__ == "__main__":
    main()
