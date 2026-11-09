terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.4, < 3.0"
    }
  }

  # Local, in a .nosync folder: one person deploys, and CI tests with a mocked provider.
  backend "local" {
    path = "state.nosync/dev.tfstate"
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "sa-property-lakehouse"
      ManagedBy = "terraform"
    }
  }
}
