mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }
  mock_data "aws_region" {
    defaults = {
      region = "eu-west-1"
    }
  }
}

variables {
  job_name         = "test-job"
  bucket_id        = "test-lake"
  bucket_arn       = "arn:aws:s3:::test-lake"
  script_path      = "tests/fixture.py"
  read_prefixes    = ["bronze/"]
  write_prefixes   = ["warehouse/"]
  catalog_database = "test_db"
}

run "job_cost_is_capped" {
  command = plan

  assert {
    condition     = aws_glue_job.this.number_of_workers == 2 && aws_glue_job.this.worker_type == "G.1X"
    error_message = "Use the smallest Spark cluster: 2 G.1X workers."
  }

  assert {
    condition     = aws_glue_job.this.timeout <= 15
    error_message = "A stuck job must stop quickly. The Glue default is 48 hours."
  }

  assert {
    condition     = aws_glue_job.this.max_retries == 0
    error_message = "A failing job must not rerun and bill again."
  }

  assert {
    condition     = aws_glue_job.this.execution_property[0].max_concurrent_runs == 1
    error_message = "Only one run at a time."
  }
}
