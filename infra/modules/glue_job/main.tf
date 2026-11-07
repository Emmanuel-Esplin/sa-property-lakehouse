terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
  }
}

variable "job_name" { type = string }
variable "bucket_id" { type = string }
variable "bucket_arn" { type = string }
variable "script_path" { type = string }
variable "read_prefixes" { type = list(string) }
variable "write_prefixes" { type = list(string) }
variable "catalog_database" { type = string }
variable "default_arguments" {
  type    = map(string)
  default = {}
}
variable "timeout_minutes" {
  type        = number
  default     = 10
  description = "Hard stop, so a stuck job cannot keep billing."
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  script_key = "scripts/${var.job_name}.py"
  scope      = "${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_object" "script" {
  bucket = var.bucket_id
  key    = local.script_key
  source = var.script_path
  etag   = filemd5(var.script_path)
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "permissions" {
  statement {
    sid       = "ReadScriptAndInputs"
    actions   = ["s3:GetObject"]
    resources = [for prefix in concat(["scripts/"], var.read_prefixes) : "${var.bucket_arn}/${prefix}*"]
  }

  statement {
    sid       = "ListLake"
    actions   = ["s3:ListBucket"]
    resources = [var.bucket_arn]
  }

  statement {
    sid = "WriteTables"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = [for prefix in var.write_prefixes : "${var.bucket_arn}/${prefix}*"]
  }

  statement {
    sid = "UseCatalogDatabase"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:DeleteTable",
    ]
    resources = [
      "arn:aws:glue:${local.scope}:catalog",
      "arn:aws:glue:${local.scope}:database/${var.catalog_database}",
      "arn:aws:glue:${local.scope}:table/${var.catalog_database}/*",
    ]
  }

  statement {
    sid     = "WriteJobLogs"
    actions = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [
      "arn:aws:logs:${local.scope}:log-group:/aws-glue/*",
    ]
  }
}

resource "aws_iam_role" "job" {
  name               = var.job_name
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy" "job" {
  name   = "least-privilege"
  role   = aws_iam_role.job.id
  policy = data.aws_iam_policy_document.permissions.json
}

resource "aws_glue_job" "this" {
  name              = var.job_name
  role_arn          = aws_iam_role.job.arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  max_retries       = 0
  timeout           = var.timeout_minutes
  default_arguments = var.default_arguments

  execution_property {
    max_concurrent_runs = 1
  }

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${var.bucket_id}/${local.script_key}"
  }
}

output "job_name" { value = aws_glue_job.this.name }
