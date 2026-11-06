# SA Property Lakehouse

A data platform that answers the questions a South African property owner asks about its tenants
and its market. It has two domains: **tenant trading**, built from national retail sales, and
**REIT market performance**, which is planned.

> **Status: Phase 1 complete, Phase 2 verified on AWS.** Tenant trading runs locally on real data
> through the August 2026 release. The AWS foundation was deployed to a dev account and tested with
> real data. That account is temporary, so the environment may be torn down. Marts still build
> locally: Spark, dbt and the REIT module are planned.

## What the data shows

Latest 12 months (September 2025 to August 2026) against the 12 before. CPI averaged 3.8%.

| Retailer type | Segment | Sales growth | Volume | Implied price | Beat CPI? |
|---|---|---:|---:|---:|---|
| Pharmaceuticals and cosmetics | Defensive | 6.5% | 3.5% | 3.0% | Yes |
| All other retailers | Mixed | 5.8% | 7.4% | -1.5% | Yes |
| Food, beverages and tobacco | Defensive | 5.1% | **-1.1%** | 6.3% | Yes |
| Furniture and appliances | Discretionary | 4.7% | 8.9% | -3.8% | Yes |
| General dealers | Defensive | 4.0% | 1.7% | 2.3% | Yes, by 0.2 points |
| Clothing and footwear | Discretionary | 3.4% | 2.9% | 0.5% | No, by 0.4 points |
| Hardware, paint and glass | Discretionary | 2.3% | 0.7% | 1.6% | No |
| **All retailers** | | **4.3%** | **2.7%** | **1.6%** | **Yes, by 0.5 points** |

- **Volume and sales can tell opposite stories.** Furniture and appliances has the strongest volume
  growth, but falling implied prices cut its sales growth to 4.7%. Rent linked to turnover follows
  sales, not volume. Specialist food beat CPI while selling less.
- **Defensive categories are growing on price.** They grew volume 1.5% on sales growth of 4.5%.
  Discretionary categories grew volume 3.2% on sales growth of 3.3%.
- **Hardware is the weakest.** It has the lowest sales growth, with volume down year on year in 12
  of the last 24 months, including each of the last four.
- **Clothing is the most seasonal.** December runs at 1.80 times an average month, against 1.30 for
  general dealers and 1.08 for pharmacy. A clothing tenant's year depends far more on one month.

The latest months are preliminary, and Stats SA revises them. CPI covers services as well as goods,
so "beat CPI" is a benchmark rather than a like-for-like price comparison. Small margins, such as
general dealers and clothing, could flip with revisions.

**Checked against the source.** All 101 growth rates compared with Stats SA's August 2026 release
match at one decimal place: every category for six months at both price bases, plus five annual
totals. Run `make reconcile` to repeat this.

## Questions

Module 2, tenant trading, comes first:

1. How has retail turnover grown over the last 24 months, by retailer type?
2. How much of that growth is real, and how much is price?
3. Which categories are growing above CPI, and which are shrinking in real terms?
4. Which categories are most seasonal, and how do defensive and discretionary categories compare?

See [docs/business-questions.md](docs/business-questions.md) for how each one is answered.

**What this data can't show.** Stats SA's retail trade sales are national figures by retailer type,
not tenant turnover. Growth here compares the same category in the same month a year apart. It is
not same-store growth, because store openings and closures are included. Use it as a market
benchmark: a landlord can compare its own tenants' like-for-like growth against it.

## How it works

```mermaid
flowchart LR
    S[Stats SA P6242.1] -->|manual browser download| L[Landing]
    L --> B[(Bronze: every vintage, hashed)]
    R[SARB API: CPI] -->|scripted| B
    B -->|validated contract| SV[(Silver: tidy Parquet)]
    SV -->|DuckDB SQL + checks| G[(Gold: marts)]
```

The main decisions are explained in [docs/design-decisions.md](docs/design-decisions.md), and every
column is described in [docs/data-dictionary.md](docs/data-dictionary.md).

## Run it

Requires Python 3.12 or later. `make install` uses `/opt/anaconda3/bin/python` by default; override
it with `BOOTSTRAP_PYTHON=python3.12`.

```bash
make install
make test
make cpi       # fetch CPI from SARB
```

Retail data takes one manual step, because Stats SA's site blocks scripted clients:

1. In a browser, go to [statssa.gov.za](https://www.statssa.gov.za) and download the time series
   data for release P6242.1, Retail trade sales.
2. Put the Excel workbook (`.xlsx`) anywhere under `data/landing/stats_sa/retail_trade/`. Keep only
   the latest one there: other formats are ignored, and two workbooks stop the run.
3. Run `make retail`, then `make gold`.

Marts are written to `data/gold/`.

## AWS

`make tf-check` validates the Terraform and needs no AWS account. Deploying needs AWS credentials
and a `terraform.tfvars` copied from the example in `infra/envs/dev/`:

```bash
make tf-plan      # review what would be created
make tf-apply     # creates billable resources
make tf-destroy   # removes everything, including the data in the bucket
```

The cost design and guardrails are in [docs/aws-costs.md](docs/aws-costs.md).

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 1 | Local ingestion and DuckDB marts for tenant trading | Done |
| 2 | Terraform: S3, IAM, Glue; ingestion on Lambda | Done, verified on AWS |
| 3 | PySpark bronze to silver to gold with Iceberg or Delta | Planned |
| 4 | dbt marts for both modules | Planned |
| 5 | REIT module: market prices and SARB rates | Planned |
| 6 | Orchestration and Terraform plan in CI | Planned |
| 7 | Dashboard and written findings | Planned |

## Data sources

Retail trade sales: Statistics South Africa, release P6242.1. CPI: South African Reserve Bank web
API, series `CPI1000F`. Source data is not stored in this repository.

## License

[MIT](LICENSE)
