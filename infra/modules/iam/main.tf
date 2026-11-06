terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
  }
}

variable "role_name" { type = string }
variable "log_group_arn" { type = string }
variable "bucket_arn" { type = string }
variable "read_prefixes" {
  type    = list(string)
  default = []
}
variable "write_prefixes" {
  type = list(string)
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "permissions" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${var.log_group_arn}:*"]
  }

  statement {
    sid       = "WritePrefixes"
    actions   = ["s3:PutObject"]
    resources = [for prefix in var.write_prefixes : "${var.bucket_arn}/${prefix}*"]
  }

  dynamic "statement" {
    for_each = length(var.read_prefixes) > 0 ? [1] : []
    content {
      sid       = "ReadPrefixes"
      actions   = ["s3:GetObject"]
      resources = [for prefix in var.read_prefixes : "${var.bucket_arn}/${prefix}*"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = var.role_name
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy" "this" {
  name   = "least-privilege"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.permissions.json
}

output "role_arn" { value = aws_iam_role.this.arn }
