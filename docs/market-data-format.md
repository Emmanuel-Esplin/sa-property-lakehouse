# REIT market data format

REIT prices and distributions come from CSV files you download yourself, from a source whose terms
allow this use. The project doesn't fetch them, because no free source found so far allows
automated downloads of JSE prices.

Export from your source into the format below, then run `make reits` and `make gold`.

## Where files go

| Kind | Folder |
| --- | --- |
| Daily closing prices | `data/landing/market/prices/` |
| Distributions per share | `data/landing/market/distributions/` |

Use any number of `.csv` files, such as one per REIT. The files in these folders are the current
data. Each version is also kept in bronze, so replacing a file doesn't lose its history.

## Prices

```csv
date,ticker,close_cents
2026-01-05,VKE,1500
2026-01-06,VKE,1510
```

| Column | Rule |
| --- | --- |
| `date` | A trading day, written `YYYY-MM-DD` |
| `ticker` | A JSE ticker listed in `transform/seeds/reits.csv` |
| `close_cents` | The closing price **in cents**, as the JSE quotes it. R15.00 is `1500` |

## Distributions

```csv
ticker,ex_date,amount_cents
VKE,2026-03-18,61.5
```

| Column | Rule |
| --- | --- |
| `ticker` | A JSE ticker listed in `transform/seeds/reits.csv` |
| `ex_date` | The first day the share trades without the distribution, written `YYYY-MM-DD` |
| `amount_cents` | The distribution per share **in cents** |

## What gets a file refused

Every check names the file, and the value or ticker that failed it.

| Check | Why |
| --- | --- |
| Columns other than the ones above | The format is fixed, so a changed export can't be misread |
| A date or number that won't parse | No value is guessed |
| A ticker not in the seed | Every REIT needs a sector for the sector questions |
| A price that moves more than 50% in a day | Usually prices in rand mixed with prices in cents |
| More than 14 days without a price | A missing stretch would distort that REIT's returns |
| The same ticker and date with different values | Overlapping downloads that disagree. Identical repeats are fine |
| A distribution outside its REIT's price history | It couldn't enter any return, so it's likely a typo |

If anything is refused, silver is left as it was.

## Adding a REIT

Add a row to `transform/seeds/reits.csv` with its ticker, name and main sector: `retail`,
`logistics`, `office`, `diversified` or `specialist`. The sectors in the seed are this project's
judgement, so change them if you see a REIT differently. Check that each ticker matches the one your
source uses.

## What the marts calculate

- **Total return** for a month is the change in month-end price plus distributions that went ex in
  that month. It treats a distribution as received at month end.
- **Distribution yield** is the last 12 months of distributions over the month-end price. It appears
  only once 12 months of prices exist.
- **3- and 5-year returns** are annualised, and shown only when every month in the window has a
  return. Real returns remove CPI over the same years.
- **Sector sensitivity** compares each sector's monthly return in months when the policy rate went
  up, down or stayed the same. Rate changes are rare, so read the month counts alongside it.

The latest month is left out until it ends, as in every other mart.
