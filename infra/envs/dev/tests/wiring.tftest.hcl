mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}

variables {
  alert_email = "alerts@example.com"
}

run "dev_environment_fits_together" {
  command = plan

  assert {
    condition     = output.lake_bucket == "sa-property-lakehouse-123456789012"
    error_message = "The bucket name must include the account ID, because names are global."
  }

  assert {
    condition     = one(aws_s3_bucket_notification.landing.lambda_function).filter_prefix == "landing/stats_sa/"
    error_message = "Only landing may trigger the retail Lambda, or it could trigger itself."
  }

  assert {
    condition     = aws_cloudwatch_log_group.cpi.retention_in_days == 14 && aws_cloudwatch_log_group.retail.retention_in_days == 14
    error_message = "Logs must expire so they do not accumulate cost."
  }

  assert {
    condition     = aws_athena_workgroup.lakehouse.configuration[0].bytes_scanned_cutoff_per_query <= 1073741824
    error_message = "Athena queries must stop at 1 GB scanned."
  }

  assert {
    condition     = aws_athena_workgroup.lakehouse.configuration[0].enforce_workgroup_configuration
    error_message = "Clients must not be able to override the workgroup's limits."
  }
}
