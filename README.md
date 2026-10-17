# Cold cereal price discounts

Do cold-cereal price cuts sell enough extra boxes to cover the discount, and how high does gross margin need to be for that to happen?

Discount weeks sold **7,291 extra boxes**, 72% above the full-price pace of the same cereals. Anything under **52%** loses money during the discount weeks. The tie is **52.4%**: a gross margin below it loses money, and a margin above it does not.

![Change in margin dollars during discount weeks](docs/figures/margin-dollars.png)

The full comparison, household and product breakdowns, campaign check, and limits are in [docs/FINDINGS.md](docs/FINDINGS.md).

## Data

The source is Dunnhumby's Complete Journey: 2,500 households and 711 days of purchases at one retailer.

- Dataset: [frtgnn/dunnhumby-the-complete-journey](https://www.kaggle.com/datasets/frtgnn/dunnhumby-the-complete-journey)
- License: [DbCL-1.0](https://opendatacommons.org/licenses/dbcl/1-0/)

The scripts read a parquet copy of those tables. Retail discounts are stored as positive dollars, and `GROSS_SALES` is already on the transaction file. The copy is published at [bltap-plmarket/dunnhumby-complete-journey](https://github.com/bltap-plmarket/dunnhumby-complete-journey/tree/main/data/parquet_parking). The raw files are not committed here.

From the project folder:

```bash
mkdir -p data/parquet
base=https://raw.githubusercontent.com/bltap-plmarket/dunnhumby-complete-journey/main/data/parquet_parking
for file in fact_transactions.parquet dim_product.parquet dim_household.parquet dim_campaign.parquet fact_campaign_received.parquet
do
  curl -fsSL -o "data/parquet/$file" "$base/$file"
done
```

## Run

Python 3.12 is the version used for these results.

```bash
python3 -m pip install -r requirements.txt
python3 analysis/cereal_extra_units.py   # extra boxes, margin tie, and the one-week and four-week check
python3 analysis/cereal_story.py         # household, cereal type, brand, and campaign breakdowns
python3 analysis/build_figures.py        # the four figures in docs/FINDINGS.md
```

`analysis/profile_discounts.py` compares how often prices were cut across departments. That comparison is why the findings are limited to cold cereal.
