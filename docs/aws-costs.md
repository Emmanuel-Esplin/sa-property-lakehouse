# AWS costs and guardrails

The project is designed to fit well inside a small credit balance. Prices are approximate, so check
AWS's pricing pages before relying on them.

## What Phase 2 deploys

| Resource | Why it is cheap | Expected monthly cost |
| --- | --- | --- |
| S3 lake | A few MB of data | Under $0.01 |
| 2 Lambda functions | A few runs a month, on arm64 | Under $0.01 |
| EventBridge schedule | Weekly | Effectively $0 |
| CloudWatch logs | Small, kept for 14 days | Under $0.01 |
| Glue database | Catalog entry only, no jobs or crawlers | Effectively $0 |
| AWS Budget | Within the free allowance | $0 |

There is no VPC, NAT gateway or always-on compute, so almost nothing bills while idle.

## Later phases

| Phase | Service | Approximate price | Note |
| --- | --- | --- | --- |
| 3 | Glue Spark jobs | $0.44 per DPU-hour | Measured: 147 and 227 DPU-seconds, about 5 cents for both jobs. They run on demand |
| 4 | Athena through dbt | $5 per TB scanned, at least 10 MB a query | A full build scans a few MB. Each query costs about $0.00005, and the workgroup stops any query at 1 GB |
| 6 | Step Functions, CodeBuild, SNS | $0.025 per 1,000 state transitions; about $0.005 a build minute | A run is about 10 transitions and a 2-minute dbt build. A week with nothing new stops after ingestion |

## Services to avoid here

These are priced for production workloads and would use up the credits quickly:

| Service | Approximate cost | Use instead |
| --- | --- | --- |
| Managed Airflow (MWAA) | Over $300 a month, even idle | EventBridge, Step Functions or local Airflow |
| NAT gateway | Over $30 a month, even idle | No VPC: Lambda reaches the internet by default |
| Redshift, RDS, EMR clusters | Bill while running | Athena on S3 |

## Guardrails

- **The budget ignores credits.** Otherwise spend is netted against credits, the bill looks like $0,
  and alerts stay silent while the balance falls. A Terraform test enforces this.
- **A budget alerts but doesn't stop spending,** and its figures can lag by hours. Run
  `make tf-destroy` when the project isn't in active use.
- **Teardown is complete.** `force_destroy` lets `make tf-destroy` empty the bucket too, including
  bronze. Stats SA workbooks are also kept locally. Older SARB responses exist only in bronze.
- **State is local,** because only one person deploys this. CI checks the Terraform with a mocked
  provider, so it needs no AWS credentials.

## Verified on AWS

Deployed on 6 November 2026 and tested with real data:

- The CPI Lambda reached the live SARB API from AWS, and a repeat run wrote nothing.
- Uploading the real workbook triggered the retail Lambda, and the bronze copy's checksum matched.
- A renamed copy of the workbook added nothing to bronze. An HTML file saved as `.xlsx` was rejected.
- Anonymous requests for a bronze object returned 403.

Phase 3 ran on 7 November 2026 on the Free plan. Both Glue jobs succeeded, and their output matched
the local marts and the published figures.

Each job has 2 workers, no retries, one run at a time and a 10-minute timeout, because Glue's default
timeout is 48 hours. A Terraform test enforces these limits.

Phase 4 ran the same day. dbt built and tested 35 models and tests on Athena, and the marts matched
the local marts and the published figures. The Spark gold job was removed, because dbt replaced it.

Phase 5 added SARB interest rates. The Lambda now fetches four series, and the Spark job used 174
DPU-seconds, about 2 cents. All six marts, 2,205 rows, matched the local marts.

Phase 6 ran on 9 November 2026. A forced run took under 5 minutes: Spark used 267 DPU-seconds,
about 3 cents, and the dbt build took under 2 minutes, about 1 cent. The marts matched the local
marts on all 2,205 rows and all 101 published figures. A weekly run and a re-uploaded workbook
with nothing new both stopped after ingestion. The first run failed on a missing Glue permission
for dbt, and the failure email arrived.

## Credit rules

AWS's rules depend on the account plan, so check the Billing console. On the
[Free plan](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html), the
account closes after 6 months or when credits run out, unless it is upgraded, and some services are
restricted. Credits expire 12 months after the account is created. Joining AWS Organizations ends
Free Tier credits immediately.
