# Runs dbt on Athena in CodeBuild. dbt is too large for Lambda, and a build is billed only while it runs.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
  }
}

variable "project_name" { type = string }
variable "bucket_id" { type = string }
variable "bucket_arn" { type = string }
variable "source_key" {
  type        = string
  description = "S3 key of the zip holding transform/ and what it imports."
}
variable "workgroup" { type = string }
variable "databases" {
  type        = list(string)
  description = "Glue databases dbt reads (silver) and writes (marts)."
}
variable "timeout_minutes" {
  type        = number
  default     = 20
  description = "Hard stop, so a stuck build cannot keep billing."
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  scope     = "${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}"
  log_group = "/aws/codebuild/${var.project_name}"
}

resource "aws_cloudwatch_log_group" "build" {
  name              = local.log_group
  retention_in_days = 14
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "permissions" {
  statement {
    sid       = "ReadSource"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${var.bucket_arn}/${var.source_key}"]
  }

  statement {
    sid       = "ListLake"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [var.bucket_arn]
  }

  # Silver tables live under warehouse/. dbt only reads them.
  statement {
    sid       = "ReadSilver"
    actions   = ["s3:GetObject"]
    resources = ["${var.bucket_arn}/warehouse/*"]
  }

  # Query results, and the marts dbt writes.
  statement {
    sid = "WriteResultsAndMarts"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = [
      "${var.bucket_arn}/athena-results/*",
      "${var.bucket_arn}/marts/*",
    ]
  }

  statement {
    sid = "QueryAthena"
    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:StopQueryExecution",
      "athena:GetWorkGroup",
    ]
    resources = ["arn:aws:athena:${local.scope}:workgroup/${var.workgroup}"]
  }

  statement {
    sid = "UseCatalog"
    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetPartitions",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:DeleteTable",
      "glue:BatchDeleteTable",
      # dbt-athena prunes old table versions after each build, and manages partitions.
      "glue:GetTableVersions",
      "glue:DeleteTableVersion",
      "glue:BatchCreatePartition",
      "glue:BatchDeletePartition",
    ]
    resources = concat(
      ["arn:aws:glue:${local.scope}:catalog"],
      [for db in var.databases : "arn:aws:glue:${local.scope}:database/${db}"],
      [for db in var.databases : "arn:aws:glue:${local.scope}:table/${db}/*"],
    )
  }

  statement {
    sid       = "WriteBuildLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.build.arn}:*"]
  }
}

resource "aws_iam_role" "build" {
  name               = var.project_name
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy" "build" {
  name   = "least-privilege"
  role   = aws_iam_role.build.id
  policy = data.aws_iam_policy_document.permissions.json
}

resource "aws_codebuild_project" "dbt" {
  name          = var.project_name
  service_role  = aws_iam_role.build.arn
  build_timeout = var.timeout_minutes

  source {
    type      = "S3"
    location  = "${var.bucket_id}/${var.source_key}"
    buildspec = file("${path.module}/buildspec.yml")
  }

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type = "BUILD_GENERAL1_SMALL"
    image        = "aws/codebuild/amazonlinux-x86_64-standard:5.0"
    type         = "LINUX_CONTAINER"

    environment_variable {
      name  = "LAKE_BUCKET"
      value = var.bucket_id
    }

    # dbt writes its target and logs here, inside the build container.
    environment_variable {
      name  = "LAKEHOUSE_DATA_DIR"
      value = "/tmp/lakehouse"
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name = aws_cloudwatch_log_group.build.name
    }
  }
}

output "project_name" { value = aws_codebuild_project.dbt.name }
output "project_arn" { value = aws_codebuild_project.dbt.arn }
