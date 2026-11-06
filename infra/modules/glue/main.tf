terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
  }
}

variable "database_name" { type = string }

# The catalog only. Glue jobs and crawlers are what cost money, and they arrive in Phase 3.
resource "aws_glue_catalog_database" "lake" {
  name = var.database_name
}

output "database_name" { value = aws_glue_catalog_database.lake.name }
