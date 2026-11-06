terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
  }
}

variable "function_name" { type = string }
variable "handler" { type = string }
variable "role_arn" { type = string }
variable "zip_path" { type = string }
variable "zip_hash" { type = string }
variable "environment" { type = map(string) }
variable "log_group_name" { type = string }

resource "aws_lambda_function" "this" {
  function_name    = var.function_name
  role             = var.role_arn
  handler          = var.handler
  runtime          = "python3.13"
  architectures    = ["arm64"]
  memory_size      = 256
  timeout          = 120
  filename         = var.zip_path
  source_code_hash = var.zip_hash

  logging_config {
    log_format = "Text"
    log_group  = var.log_group_name
  }

  environment {
    variables = var.environment
  }
}

output "arn" { value = aws_lambda_function.this.arn }
output "name" { value = aws_lambda_function.this.function_name }
