data "aws_caller_identity" "current" {}

locals {
  name       = "sa-property-lakehouse"
  bucket     = "${local.name}-${data.aws_caller_identity.current.account_id}"
  repo_root  = "${path.module}/../../.."
  lambda_src = "${local.repo_root}/ingestion"
  glue_arguments = {
    "--LAKE_BUCKET"      = local.bucket
    "--datalake-formats" = "iceberg"
    "--extra-py-files"   = "s3://${local.bucket}/${aws_s3_object.lakehouse_zip.key}"
  }
  log_prefix = "/aws/lambda/${local.name}"
  # Everything the handlers import. Tests prove that excludes pandas and friends.
  lambda_files = [
    "__init__.py",
    "lambda_handlers.py",
    "common/__init__.py",
    "common/s3_writer.py",
    "sarb/__init__.py",
    "sarb/client.py",
    "sarb/series.py",
  ]
}

# Created first, so spend is watched from the start.
module "budget" {
  source            = "../../modules/budget"
  name              = "${local.name}-monthly"
  monthly_limit_usd = var.monthly_budget_usd
  alert_email       = var.alert_email
}

module "lake" {
  source        = "../../modules/s3_lake"
  bucket_name   = local.bucket
  force_destroy = true
}

module "glue" {
  source        = "../../modules/glue"
  database_name = "sa_property_lakehouse"
}

data "archive_file" "ingestion" {
  type        = "zip"
  output_path = "${path.module}/build.nosync/ingestion.zip"

  dynamic "source" {
    for_each = toset(local.lambda_files)
    content {
      content  = file("${local.lambda_src}/${source.value}")
      filename = "ingestion/${source.value}"
    }
  }
}

resource "aws_cloudwatch_log_group" "sarb" {
  name              = "${local.log_prefix}-sarb"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "retail" {
  name              = "${local.log_prefix}-retail"
  retention_in_days = 14
}

module "sarb_role" {
  source         = "../../modules/iam"
  role_name      = "${local.name}-sarb"
  log_group_arn  = aws_cloudwatch_log_group.sarb.arn
  bucket_arn     = module.lake.bucket_arn
  write_prefixes = ["bronze/sarb/"]
}

module "retail_role" {
  source         = "../../modules/iam"
  role_name      = "${local.name}-retail"
  log_group_arn  = aws_cloudwatch_log_group.retail.arn
  bucket_arn     = module.lake.bucket_arn
  read_prefixes  = ["landing/stats_sa/"]
  write_prefixes = ["bronze/stats_sa/"]
}

module "sarb_lambda" {
  source         = "../../modules/lambda"
  function_name  = "${local.name}-sarb"
  handler        = "ingestion.lambda_handlers.sarb_handler"
  role_arn       = module.sarb_role.role_arn
  zip_path       = data.archive_file.ingestion.output_path
  zip_hash       = data.archive_file.ingestion.output_base64sha256
  log_group_name = aws_cloudwatch_log_group.sarb.name
  environment    = { LAKE_BUCKET = module.lake.bucket_name }
}

module "retail_lambda" {
  source         = "../../modules/lambda"
  function_name  = "${local.name}-retail"
  handler        = "ingestion.lambda_handlers.retail_handler"
  role_arn       = module.retail_role.role_arn
  zip_path       = data.archive_file.ingestion.output_path
  zip_hash       = data.archive_file.ingestion.output_base64sha256
  log_group_name = aws_cloudwatch_log_group.retail.name
  environment    = { LAKE_BUCKET = module.lake.bucket_name }
}

# The pipeline module's EventBridge rule picks out uploads to landing/stats_sa/. Only that prefix
# starts a run, and the run writes only outside landing/, so it cannot trigger itself.
resource "aws_s3_bucket_notification" "landing" {
  bucket      = module.lake.bucket_id
  eventbridge = true
}

output "lake_bucket" {
  value = module.lake.bucket_name
}

output "retail_upload_command" {
  value = "aws s3 cp <workbook.xlsx> s3://${module.lake.bucket_name}/landing/stats_sa/"
}

output "sarb_lambda" {
  value = module.sarb_lambda.name
}

# Glue writes to these groups. Created here so logs expire and a destroy removes them.
resource "aws_cloudwatch_log_group" "glue" {
  for_each          = toset(["output", "error", "logs-v2"])
  name              = "/aws-glue/jobs/${each.value}"
  retention_in_days = 14
}

# Everything the Glue job imports.
data "archive_file" "lakehouse" {
  type        = "zip"
  output_path = "${path.module}/build.nosync/lakehouse.zip"

  dynamic "source" {
    for_each = setunion(
      fileset(local.repo_root, "ingestion/**/*.py"),
      fileset(local.repo_root, "processing/**/*.py"),
    )
    content {
      content  = file("${local.repo_root}/${source.value}")
      filename = source.value
    }
  }
}

resource "aws_s3_object" "lakehouse_zip" {
  bucket = module.lake.bucket_id
  key    = "scripts/lakehouse.zip"
  source = data.archive_file.lakehouse.output_path
  etag   = data.archive_file.lakehouse.output_md5
}

module "glue_bronze_to_silver" {
  source           = "../../modules/glue_job"
  job_name         = "${local.name}-bronze-to-silver"
  bucket_id        = module.lake.bucket_id
  bucket_arn       = module.lake.bucket_arn
  script_path      = "${local.repo_root}/processing/bronze_to_silver/job.py"
  read_prefixes    = ["bronze/"]
  write_prefixes   = ["warehouse/"]
  catalog_database = module.glue.database_name
  default_arguments = merge(local.glue_arguments, {
    "--additional-python-modules" = "openpyxl==3.1.5"
  })
  depends_on = [aws_cloudwatch_log_group.glue]
}

# dbt on Athena writes the marts here. Terraform owns it, so a destroy removes the tables too.
module "glue_marts" {
  source        = "../../modules/glue"
  database_name = "sa_property_lakehouse_marts"
}

resource "aws_athena_workgroup" "lakehouse" {
  name          = local.name
  force_destroy = true

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = false
    # Athena bills per TB scanned. The marts are a few MB, so anything near 1 GB is a mistake.
    bytes_scanned_cutoff_per_query = 1073741824

    engine_version {
      selected_engine_version = "Athena engine version 3"
    }

    result_configuration {
      output_location = "s3://${module.lake.bucket_name}/athena-results/"
      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

# --- Orchestration ---------------------------------------------------------------------------

# dbt and only what it imports: transform/ and the data_dir helper.
data "archive_file" "dbt" {
  type        = "zip"
  output_path = "${path.module}/build.nosync/dbt.zip"

  dynamic "source" {
    for_each = setunion(
      fileset(local.repo_root, "transform/*.{py,yml,txt}"),
      fileset(local.repo_root, "transform/{models,macros,seeds,tests}/**"),
      ["ingestion/__init__.py", "ingestion/common/__init__.py", "ingestion/common/bronze.py"],
    )
    content {
      content  = file("${local.repo_root}/${source.value}")
      filename = source.value
    }
  }
}

resource "aws_s3_object" "dbt_zip" {
  bucket = module.lake.bucket_id
  key    = "scripts/dbt.zip"
  source = data.archive_file.dbt.output_path
  etag   = data.archive_file.dbt.output_md5
}

module "dbt_runner" {
  source       = "../../modules/dbt_runner"
  project_name = "${local.name}-dbt"
  bucket_id    = module.lake.bucket_id
  bucket_arn   = module.lake.bucket_arn
  source_key   = aws_s3_object.dbt_zip.key
  workgroup    = aws_athena_workgroup.lakehouse.name
  databases    = [module.glue.database_name, module.glue_marts.database_name]
}

module "pipeline" {
  source            = "../../modules/pipeline"
  name              = local.name
  sarb_lambda_arn   = module.sarb_lambda.arn
  retail_lambda_arn = module.retail_lambda.arn
  glue_job_name     = module.glue_bronze_to_silver.job_name
  dbt_project_name  = module.dbt_runner.project_name
  dbt_project_arn   = module.dbt_runner.project_arn
  bucket_name       = module.lake.bucket_name
  alert_email       = var.alert_email
}

# The weekly SARB rule now starts the pipeline instead of the Lambda. Moving it keeps the rule
# rather than deleting and recreating one with the same name.
moved {
  from = aws_cloudwatch_event_rule.sarb
  to   = module.pipeline.aws_cloudwatch_event_rule.weekly
}

moved {
  from = aws_cloudwatch_event_target.sarb
  to   = module.pipeline.aws_cloudwatch_event_target.weekly
}

output "glue_jobs" {
  value = [module.glue_bronze_to_silver.job_name]
}

output "state_machine" {
  value = module.pipeline.state_machine_arn
}

output "athena_workgroup" {
  value = aws_athena_workgroup.lakehouse.name
}
