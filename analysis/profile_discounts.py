"""Count how often a receipt price was cut, and how large the cut was.

A purchase line is one product inside one shopping trip. In this copy of the
data the retail discount is already a positive dollar amount. A line is on
discount when that amount is above zero.

The price before the discount is the amount the shopper paid plus the
discount. Discount depth is the discount divided by that pre-discount price.
"""

from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data" / "parquet"
OUT = Path(__file__).resolve().parents[1] / "data" / "discount_profile.csv"

# Categories with enough full-price and discounted lines to compare later.
CANDIDATES = [
    "SOFT DRINKS",
    "BEEF",
    "FLUID MILK PRODUCTS",
    "CHEESE",
    "BAG SNACKS",
    "COLD CEREAL",
    "SOUP",
    "ICE CREAM/MILK/SHERBTS",
]


def main() -> None:
    transactions = pd.read_parquet(DATA / "fact_transactions.parquet")
    products = pd.read_parquet(DATA / "dim_product.parquet")
    lines = transactions.merge(
        products[["PRODUCT_ID", "DEPARTMENT", "COMMODITY_DESC"]],
        on="PRODUCT_ID",
        how="left",
    )

    on_discount = lines["RETAIL_DISC"] > 0
    pre_discount_price = lines["GROSS_SALES"]
    discounted = lines.loc[on_discount & pre_discount_price.gt(0)].copy()
    discounted["depth"] = discounted["RETAIL_DISC"] / discounted["GROSS_SALES"]

    line_count = len(lines)
    print(f"Purchase lines: {line_count:,}")
    print(f"Households: {lines['household_key'].nunique():,}")
    print(f"Shopping trips: {lines['BASKET_ID'].nunique():,}")
    print(f"Lines with a price cut: {on_discount.mean():.1%}")
    print(f"Typical cut on those lines: {discounted['depth'].median():.1%} off")
    print(
        "Discount dollars as a share of pre-discount sales: "
        f"{lines['RETAIL_DISC'].sum() / lines['GROSS_SALES'].sum():.1%}"
    )
    print(f"Retail discounts: ${lines['RETAIL_DISC'].sum():,.0f}")
    print(f"Coupon discounts: ${lines['COUPON_DISC'].sum():,.0f}")

    grouped = (
        lines.groupby(["DEPARTMENT", "COMMODITY_DESC"], as_index=False)
        .agg(
            lines=("PRODUCT_ID", "size"),
            discounted_lines=("RETAIL_DISC", lambda s: int((s > 0).sum())),
            amount_paid=("SALES_VALUE", "sum"),
            pre_discount_sales=("GROSS_SALES", "sum"),
            discount_dollars=("RETAIL_DISC", "sum"),
            products=("PRODUCT_ID", "nunique"),
        )
    )
    chosen = grouped[grouped["COMMODITY_DESC"].isin(CANDIDATES)].copy()
    chosen["share_of_lines_discounted"] = chosen["discounted_lines"] / chosen["lines"]
    chosen["average_cut"] = chosen["discount_dollars"] / chosen["pre_discount_sales"]
    chosen = chosen.sort_values("amount_paid", ascending=False)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    chosen.to_csv(OUT, index=False)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
