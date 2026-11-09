mock_provider "aws" {
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
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}

variables {
  name              = "lakehouse"
  sarb_lambda_arn   = "arn:aws:lambda:eu-west-1:123456789012:function:sarb"
  retail_lambda_arn = "arn:aws:lambda:eu-west-1:123456789012:function:retail"
  glue_job_name     = "bronze-to-silver"
  dbt_project_name  = "dbt"
  dbt_project_arn   = "arn:aws:codebuild:eu-west-1:123456789012:project/dbt"
  bucket_name       = "lake"
  alert_email       = "alerts@example.com"
}

run "steps_run_in_order" {
  command = plan

  assert {
    condition     = output.definition.States.IngestSarb.Next == "AnythingNew" && output.definition.States.IngestRetail.Next == "AnythingNew"
    error_message = "Both sources must go through the same check before Spark."
  }

  assert {
    condition     = output.definition.States.AnythingNew.Choices[0].Next == "BronzeToSilver" && output.definition.States.AnythingNew.Default == "NothingNew"
    error_message = "Spark must run only when bronze changed, or when forced."
  }

  assert {
    condition     = output.definition.States.BronzeToSilver.Next == "BuildMarts" && output.definition.States.BuildMarts.End
    error_message = "dbt must run after Spark, as the last step."
  }

  assert {
    condition     = endswith(output.definition.States.BronzeToSilver.Resource, ".sync") && endswith(output.definition.States.BuildMarts.Resource, ".sync")
    error_message = "Spark and dbt must be awaited, or the next step would start too early."
  }
}

run "every_failure_sends_an_email" {
  command = plan

  assert {
    condition = alltrue([
      for name, state in output.definition.States :
      state.Catch[0].Next == "NotifyFailure" if state.Type == "Task" && name != "NotifyFailure"
    ])
    error_message = "Every task must catch its errors and notify."
  }

  assert {
    condition     = output.definition.States.NotifyFailure.Next == "Failed" && output.definition.States.Failed.Type == "Fail"
    error_message = "A notified failure must still fail the execution."
  }

  assert {
    condition     = aws_sns_topic_subscription.email.endpoint == "alerts@example.com"
    error_message = "Failures must go to the alert address."
  }
}

run "glue_retries_only_when_busy" {
  command = plan

  assert {
    condition     = output.definition.States.BronzeToSilver.Retry[0].ErrorEquals == ["Glue.ConcurrentRunsExceededException"]
    error_message = "A failed Spark job must fail the run. Only a busy job is worth waiting for."
  }
}

run "triggers_are_scoped" {
  command = plan

  assert {
    condition     = output.upload_pattern.detail.object.key[0].wildcard == "landing/stats_sa/*.xlsx"
    error_message = "Only workbooks in landing may start a run, or the pipeline could trigger itself."
  }

  assert {
    condition     = jsondecode(aws_cloudwatch_event_target.weekly.input).source == "sarb"
    error_message = "The weekly run must ingest SARB."
  }
}
