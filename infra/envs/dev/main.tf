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

resource "aws_cloudwatch_log_group" "cpi" {
  name              = "${local.log_prefix}-cpi"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "retail" {
  name              = "${local.log_prefix}-retail"
  retention_in_days = 14
}

module "cpi_role" {
  source         = "../../modules/iam"
  role_name      = "${local.name}-cpi"
  log_group_arn  = aws_cloudwatch_log_group.cpi.arn
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

module "cpi_lambda" {
  source         = "../../modules/lambda"
  function_name  = "${local.name}-cpi"
  handler        = "ingestion.lambda_handlers.cpi_handler"
  role_arn       = module.cpi_role.role_arn
  zip_path       = data.archive_file.ingestion.output_path
  zip_hash       = data.archive_file.ingestion.output_base64sha256
  log_group_name = aws_cloudwatch_log_group.cpi.name
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

# CPI is monthly, and an unchanged response writes nothing, so a weekly check is plenty.
resource "aws_cloudwatch_event_rule" "cpi" {
  name                = "${local.name}-cpi-weekly"
  schedule_expression = "cron(0 6 ? * MON *)"
}

resource "aws_cloudwatch_event_target" "cpi" {
  rule = aws_cloudwatch_event_rule.cpi.name
  arn  = module.cpi_lambda.arn
}

resource "aws_lambda_permission" "cpi_schedule" {
  statement_id  = "AllowSchedule"
  action        = "lambda:InvokeFunction"
  function_name = module.cpi_lambda.name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.cpi.arn
}

resource "aws_lambda_permission" "retail_upload" {
  statement_id   = "AllowS3Upload"
  action         = "lambda:InvokeFunction"
  function_name  = module.retail_lambda.name
  principal      = "s3.amazonaws.com"
  source_arn     = module.lake.bucket_arn
  source_account = data.aws_caller_identity.current.account_id
}

# Only landing/ triggers this and the handler only writes to bronze/, so it cannot loop.
resource "aws_s3_bucket_notification" "landing" {
  bucket     = module.lake.bucket_id
  depends_on = [aws_lambda_permission.retail_upload]

  lambda_function {
    lambda_function_arn = module.retail_lambda.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "landing/stats_sa/"
    filter_suffix       = ".xlsx"
  }
}

output "lake_bucket" {
  value = module.lake.bucket_name
}

output "retail_upload_command" {
  value = "aws s3 cp <workbook.xlsx> s3://${module.lake.bucket_name}/landing/stats_sa/"
}

output "cpi_lambda" {
  value = module.cpi_lambda.name
}

# Glue writes to these groups. Created here so logs expire and a destroy removes them.
resource "aws_cloudwatch_log_group" "glue" {
  for_each          = toset(["output", "error", "logs-v2"])
  name              = "/aws-glue/jobs/${each.value}"
  retention_in_days = 14
}

# Everything the Glue jobs import, plus the SQL and seed they read.
data "archive_file" "lakehouse" {
  type        = "zip"
  output_path = "${path.module}/build.nosync/lakehouse.zip"

  dynamic "source" {
    for_each = setunion(
      fileset(local.repo_root, "ingestion/**/*.py"),
      fileset(local.repo_root, "processing/**/*.py"),
      fileset(local.repo_root, "processing/**/*.sql"),
      fileset(local.repo_root, "transform/__init__.py"),
      fileset(local.repo_root, "transform/seeds/*.csv"),
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

module "glue_silver_to_gold" {
  source            = "../../modules/glue_job"
  job_name          = "${local.name}-silver-to-gold"
  bucket_id         = module.lake.bucket_id
  bucket_arn        = module.lake.bucket_arn
  script_path       = "${local.repo_root}/processing/silver_to_gold/job.py"
  read_prefixes     = []
  write_prefixes    = ["warehouse/", "exports/"]
  catalog_database  = module.glue.database_name
  default_arguments = local.glue_arguments
  depends_on        = [aws_cloudwatch_log_group.glue]
}

output "glue_jobs" {
  value = [module.glue_bronze_to_silver.job_name, module.glue_silver_to_gold.job_name]
}
