# Design decisions

## Stats SA arrives by manual download

Stats SA's website sits behind bot protection that serves scripted clients a JavaScript challenge,
even for PDFs and `robots.txt`. The pipeline doesn't try to defeat that. A person downloads the file
in a browser, and the pipeline takes over from the landing folder. The release is monthly, so this
costs a few minutes a month. Landing also rejects HTML files, so a saved challenge page can't enter
the lake disguised as data.

## CPI comes from SARB

The SARB web API publishes headline CPI, `CPI1000F`, and accepts scripted requests. Only the year-on-year rate is used, so no index is rebased. The
parser fails if SARB stops describing the series as a 12-term % change, as that could mean the
measure has changed.

## Bronze keeps every vintage

Stats SA revises history and rebases constant prices. Earlier releases used 2012 and 2015 bases, and
recent ones use 2019. A new release therefore isn't just an old one plus a month, so each distinct
file is stored under its hash, with its original name and origin recorded alongside. A renamed copy
of a file is the same object. Silver is built from one release at a time, which
means price bases are never spliced together.

## History starts in January 2008

The workbook is named "from 2002", but only totals go back that far. Category data starts in 2005
at current prices and 2008 at constant prices. Splitting growth into volume and price needs both, so
silver keeps only months that all 32 series share. Older archives from Stats SA, such as the release
from December 2003 on 1995 prices, use different series codes and aren't spliced in.

## The parser fails on anything unexpected

Series are identified by their labels, against an exact list of categories, price bases and
adjustments. An unknown label, a changed unit or a missing series stops the run rather than dropping
data. The workbook doesn't state its release or base year: the release PDF confirms constant prices
are on a 2019 base, and the ASCII copy of the August 2026 release matched the workbook on all 7,960
values.

## Growth uses unadjusted figures

Comparing a month with the same month a year earlier already removes most seasonality, and the
seasonality mart needs the pattern left in. Seasonally adjusted series can be kept in silver for
charting.

## Year-on-year joins on the date

`LAG(12)` returns the wrong month without warning if a row is missing. A self-join on the date
returns NULL instead. Silver also rejects month gaps, so there are two separate protections.

## Price growth is a ratio, not a subtraction

Nominal minus real growth is only an approximation, and it drifts when inflation is high.
`(1 + nominal) / (1 + real) - 1` is exact, and the gold checks assert the identity on every row.

## Seasonality skips 2020 and 2021

Lockdowns restricted what could be sold and when, so those years say little about normal seasonal
patterns. The index uses up to the five latest complete years outside that period.

## Category segments are a judgement call

Defensive and discretionary aren't Stats SA labels. General dealers, specialised food and pharmacy
are treated as defensive. Clothing, furniture and hardware are discretionary. Change the mapping in
`transform/seeds/retail_categories.csv`. An unmapped category fails the build.

## Lambda only moves files

Lambda copies source files into bronze using the standard library and the boto3 in its runtime.
Parsing needs pandas, which would add a heavy package, and Phase 3 replaces it with Spark anyway. A
test proves the handlers import no heavy dependencies. Bronze writes use `If-None-Match`, so a repeat
delivery of the same file changes nothing.

## Spark reuses the existing parser and contract

The Glue job imports the same parsing and validation code as the local pipeline. One set of rules
can't drift apart, and a change to the workbook stops both runs in the same way.

## Iceberg tables in the Glue catalog

Glue 5.0 supports Iceberg natively, so no extra JARs are needed. Delta would also have worked. Iceberg
was chosen because Athena reads and writes it through the same catalog. Each run replaces the tables,
and Iceberg keeps earlier snapshots.

## One set of dbt models for two engines

The marts were first written twice, in DuckDB SQL and Spark SQL. Two copies would drift, so one dbt
project now builds them on DuckDB locally and on Athena in AWS. The models avoid features only one
engine has, such as `QUALIFY`, and use dbt's date macros where the syntax differs. Staging is the
only engine-specific part: it reads Parquet files locally and the silver Iceberg tables on Athena.

Spark keeps the bronze to silver step, which reuses the Python parser and contract.

## Data tests live in dbt

Silver is checked twice: by the Python contract when it's written, and by dbt tests when it's read.
The dbt tests cover nulls, duplicates, month gaps, unknown categories and allowed values. The growth
identity, CPI coverage and seasonal index average are singular tests. A failing test stops the build
on both engines.

## Results are compared with the source, not just the other engine

Two engines could share a mistake. So the marts built on Athena are compared with the local marts
row by row, and separately with figures published by Stats SA. Ties in the seasonal index are the one
thing neither engine defines, and the real data has none.

## One bucket, split by prefix

Landing, bronze, silver and gold share a bucket. IAM still limits each Lambda to its own prefixes,
and one bucket keeps the S3 trigger and the teardown simple.

## Local first, DuckDB pinned below 2

Phase 1 gives a working answer before any cloud cost. DuckDB is pinned below 2.0 because 2.0.0 returned
wrong results after a same-transaction bulk insert in an earlier project.
