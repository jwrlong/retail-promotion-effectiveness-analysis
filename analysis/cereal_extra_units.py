"""Estimate extra cold-cereal units from receipt price cuts.

A product-week is on discount when at least 80% of the boxes sold that week
had a retail discount, and full price when 20% or fewer did. Cold-cereal
weeks are almost entirely one or the other, so the mixed weeks in between
are left out.

Each cereal is compared with itself. The full-price weeks set the usual
weekly pace. Extra units are the discounted-week units above that pace.
A cereal is included only when it has at least two weeks on each side, so
one unusual week cannot set the pace.

Gross margin is an assumption. Cost per box is the full-price pre-discount
price times one minus the margin. The breakeven margin is the lowest margin
at which discount weeks produce at least as many margin dollars as the
full-price pace would have.
"""

from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data" / "parquet"
OUT = Path(__file__).resolve().parents[1] / "data" / "cereal_product_lift.csv"
ON_SHARE = 0.80
OFF_SHARE = 0.20
MIN_WEEKS = 2
MARGINS = (0.25, 0.35, 0.45, 0.55, 0.65)


def product_weeks() -> pd.DataFrame:
    transactions = pd.read_parquet(DATA / "fact_transactions.parquet")
    products = pd.read_parquet(
        DATA / "dim_product.parquet",
        columns=["PRODUCT_ID", "COMMODITY_DESC", "SUB_COMMODITY_DESC", "BRAND"],
    )
    cereal = products[products["COMMODITY_DESC"].eq("COLD CEREAL")]
    lines = transactions[transactions["PRODUCT_ID"].isin(cereal["PRODUCT_ID"])]
    lines = lines.merge(cereal, on="PRODUCT_ID", how="left")
    lines["discounted_units"] = np.where(lines["RETAIL_DISC"].gt(0), lines["QUANTITY"], 0)
    grouped = lines.groupby(
        ["PRODUCT_ID", "SUB_COMMODITY_DESC", "BRAND", "WEEK_NO"],
        as_index=False,
    ).agg(
        units=("QUANTITY", "sum"),
        discounted_units=("discounted_units", "sum"),
        amount_paid=("SALES_VALUE", "sum"),
        pre_discount_sales=("GROSS_SALES", "sum"),
        discount_dollars=("RETAIL_DISC", "sum"),
    )
    grouped["discounted_share"] = grouped["discounted_units"] / grouped["units"].replace(0, np.nan)
    grouped = grouped.dropna(subset=["discounted_share"])
    grouped["state"] = np.where(
        grouped["discounted_share"].ge(ON_SHARE),
        "on",
        np.where(grouped["discounted_share"].le(OFF_SHARE), "off", "mixed"),
    )
    return grouped


def eligible_products(weeks: pd.DataFrame, min_weeks: int = MIN_WEEKS) -> pd.DataFrame:
    comparable = weeks[weeks["state"].isin(["on", "off"])]
    week_counts = comparable.groupby(["PRODUCT_ID", "state"]).size().unstack(fill_value=0)
    keep = week_counts[(week_counts["on"] >= min_weeks) & (week_counts["off"] >= min_weeks)].index
    totals = (
        comparable[comparable["PRODUCT_ID"].isin(keep)]
        .groupby(["PRODUCT_ID", "SUB_COMMODITY_DESC", "BRAND", "state"], as_index=False)
        .agg(
            units=("units", "sum"),
            weeks=("WEEK_NO", "nunique"),
            amount_paid=("amount_paid", "sum"),
            pre_discount_sales=("pre_discount_sales", "sum"),
            discount_dollars=("discount_dollars", "sum"),
        )
    )
    wide = totals.pivot(index=["PRODUCT_ID", "SUB_COMMODITY_DESC", "BRAND"], columns="state")
    wide.columns = [f"{measure}_{state}" for measure, state in wide.columns]
    wide = wide.dropna().reset_index()
    wide["full_price_weekly_units"] = wide["units_off"] / wide["weeks_off"]
    wide["discount_weekly_units"] = wide["units_on"] / wide["weeks_on"]
    wide["baseline_units"] = wide["full_price_weekly_units"] * wide["weeks_on"]
    wide["extra_units"] = (wide["discount_weekly_units"] - wide["full_price_weekly_units"]) * wide["weeks_on"]
    wide["full_price"] = wide["pre_discount_sales_off"] / wide["units_off"]
    wide["price_paid_on_discount"] = wide["amount_paid_on"] / wide["units_on"]
    return wide


def margin_change(products: pd.DataFrame, margin: float) -> float:
    cost = products["full_price"] * (1 - margin)
    full_price_margin = (products["baseline_units"] * (products["full_price"] - cost)).sum()
    discount_margin = (products["units_on"] * (products["price_paid_on_discount"] - cost)).sum()
    return float(discount_margin - full_price_margin)


def breakeven_margin(products: pd.DataFrame) -> float:
    low = 0.01
    high = 0.95
    for _ in range(40):
        mid = (low + high) / 2
        if margin_change(products, mid) < 0:
            low = mid
        else:
            high = mid
    return high


def main() -> None:
    weeks = product_weeks()
    products = eligible_products(weeks)
    extra = products["extra_units"].sum()
    baseline = products["baseline_units"].sum()
    observed = products["units_on"].sum()
    depth = products["discount_dollars_on"].sum() / products["pre_discount_sales_on"].sum()
    print(f"Cereals with at least {MIN_WEEKS} full-price weeks and {MIN_WEEKS} discount weeks: {len(products)}")
    print(f"Units during discount weeks: {observed:,.0f}")
    print(f"Units expected at the full-price pace: {baseline:,.0f}")
    print(f"Extra units: {extra:,.0f}")
    print(f"Lift: {extra / baseline:.1%}")
    print(f"Discount as a share of pre-discount sales during discount weeks: {depth:.1%}")
    print(f"Gross margin required to cover the price cut: {breakeven_margin(products):.1%}")
    for margin in MARGINS:
        print(f"  At a {margin:.0%} gross margin, discount weeks change margin dollars by ${margin_change(products, margin):,.0f}")
    print("Minimum weeks on each side:")
    for min_weeks in (1, 2, 4):
        alternate = eligible_products(weeks, min_weeks=min_weeks)
        alternate_extra = alternate["extra_units"].sum()
        alternate_baseline = alternate["baseline_units"].sum()
        print(
            f"  {min_weeks}: {len(alternate)} cereals, "
            f"{alternate_extra:,.0f} extra boxes, "
            f"lift {alternate_extra / alternate_baseline:.1%}, "
            f"tie {breakeven_margin(alternate):.1%}"
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    products.to_csv(OUT, index=False)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
