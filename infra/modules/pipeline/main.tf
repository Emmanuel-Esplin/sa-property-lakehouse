# The pipeline as one Step Functions workflow: ingest, then Spark, then dbt.
# Each step starts only when the one before succeeded, and any failure sends one email.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
  }
}

variable "name" { type = string }
variable "sarb_lambda_arn" { type = string }
variable "retail_lambda_arn" { type = string }
variable "glue_job_name" { type = string }
variable "dbt_project_name" { type = string }
variable "dbt_project_arn" { type = string }
variable "bucket_name" { type = string }
variable "alert_email" { type = string }
variable "schedule" {
  type        = string
  default     = "cron(0 6 ? * MON *)"
  description = "When SARB is checked. CPI is monthly and rates change a few times a year."
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  scope = "${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}"

  # Retried with backoff: Lambda's own transient errors, not errors raised by the handler.
  lambda_retry = [{
    ErrorEquals = [
      "Lambda.ServiceException",
      "Lambda.AWSLambdaException",
      "Lambda.SdkClientException",
      "Lambda.TooManyRequestsException",
    ]
    IntervalSeconds = 2
    MaxAttempts     = 3
    BackoffRate     = 2
  }]

  # Every task hands its error, and its own name, to NotifyFailure.
  catch = { for step in ["IngestSarb", "IngestRetail", "BronzeToSilver", "BuildMarts"] : step => [{
    ErrorEquals = ["States.ALL"]
    Next        = "NotifyFailure"
    Output      = { step = step, error = "{% $states.errorOutput %}" }
  }] }

  definition = {
    Comment       = "Ingest a source into bronze, then build silver with Spark and the marts with dbt."
    QueryLanguage = "JSONata"
    StartAt       = "Start"
    States = {
      # Input: {"source": "sarb" | "retail", "bucket", "key", "force"}. Kept as variables,
      # because each state's input is the previous state's output.
      Start = {
        Type = "Pass"
        Assign = {
          retail = "{% $states.input.source = 'retail' %}"
          force  = "{% $states.input.force = true %}"
        }
        Next = "WhichSource"
      }

      WhichSource = {
        Type    = "Choice"
        Choices = [{ Condition = "{% $retail %}", Next = "IngestRetail" }]
        Default = "IngestSarb"
      }

      IngestSarb = {
        Type      = "Task"
        Resource  = "arn:aws:states:::lambda:invoke"
        Arguments = { FunctionName = var.sarb_lambda_arn, Payload = {} }
        Output    = "{% $states.result.Payload %}"
        Retry     = local.lambda_retry
        Catch     = local.catch.IngestSarb
        Next      = "AnythingNew"
      }

      # The retail Lambda reads S3 notification records, so the upload is passed in that shape.
      IngestRetail = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Arguments = {
          FunctionName = var.retail_lambda_arn
          Payload = {
            Records = [{
              s3 = {
                bucket = { name = "{% $states.input.bucket %}" }
                object = { key = "{% $states.input.key %}" }
              }
            }]
          }
        }
        Output = "{% $states.result.Payload %}"
        Retry  = local.lambda_retry
        Catch  = local.catch.IngestRetail
        Next   = "AnythingNew"
      }

      # Bronze stores each file once, so is_new is false when the source hasn't changed.
      # Then the lake is already up to date, and Spark and dbt are skipped.
      AnythingNew = {
        Type    = "Choice"
        Choices = [{ Condition = "{% $force or $count($states.input[is_new]) > 0 %}", Next = "BronzeToSilver" }]
        Default = "NothingNew"
      }

      NothingNew = {
        Type = "Succeed"
      }

      # The Glue job runs one at a time. A second pipeline waits for the first, then runs.
      BronzeToSilver = {
        Type      = "Task"
        Resource  = "arn:aws:states:::glue:startJobRun.sync"
        Arguments = { JobName = var.glue_job_name }
        Retry = [{
          ErrorEquals     = ["Glue.ConcurrentRunsExceededException"]
          IntervalSeconds = 60
          MaxAttempts     = 5
          BackoffRate     = 2
        }]
        Catch = local.catch.BronzeToSilver
        Next  = "BuildMarts"
      }

      # dbt's tests run here too, so a mart that breaks a rule fails the pipeline.
      BuildMarts = {
        Type      = "Task"
        Resource  = "arn:aws:states:::codebuild:startBuild.sync"
        Arguments = { ProjectName = var.dbt_project_name }
        Catch     = local.catch.BuildMarts
        End       = true
      }

      NotifyFailure = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish"
        Arguments = {
          TopicArn = aws_sns_topic.failures.arn
          Subject  = "${var.name}: pipeline failed"
          Message  = "{% 'Step ' & $states.input.step & ' failed with ' & $states.input.error.Error & '. ' & $substring($string($states.input.error.Cause), 0, 4000) %}"
        }
        Next = "Failed"
      }

      Failed = {
        Type  = "Fail"
        Error = "PipelineFailed"
        Cause = "A step failed. The email to the alert address has the details."
      }
    }
  }
}

# --- Failure email ---------------------------------------------------------------------------

resource "aws_sns_topic" "failures" {
  name = "${var.name}-failures"
}

# AWS emails a confirmation link first. Nothing is delivered until it's clicked.
resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.failures.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# --- State machine ---------------------------------------------------------------------------

data "aws_iam_policy_document" "states_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "states" {
  statement {
    sid       = "InvokeIngestion"
    actions   = ["lambda:InvokeFunction"]
    resources = [var.sarb_lambda_arn, var.retail_lambda_arn]
  }

  statement {
    sid       = "RunGlueJob"
    actions   = ["glue:StartJobRun", "glue:GetJobRun", "glue:GetJobRuns", "glue:BatchStopJobRun"]
    resources = ["arn:aws:glue:${local.scope}:job/${var.glue_job_name}"]
  }

  statement {
    sid       = "RunDbtBuild"
    actions   = ["codebuild:StartBuild", "codebuild:StopBuild", "codebuild:BatchGetBuilds"]
    resources = [var.dbt_project_arn]
  }

  # Step Functions waits for a CodeBuild build through this rule, which it manages itself.
  statement {
    sid       = "WaitForBuild"
    actions   = ["events:PutTargets", "events:PutRule", "events:DescribeRule"]
    resources = ["arn:aws:events:${local.scope}:rule/StepFunctionsGetEventForCodeBuildStartBuildRule"]
  }

  statement {
    sid       = "NotifyFailure"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.failures.arn]
  }
}

resource "aws_iam_role" "states" {
  name               = "${var.name}-pipeline"
  assume_role_policy = data.aws_iam_policy_document.states_assume.json
}

resource "aws_iam_role_policy" "states" {
  name   = "least-privilege"
  role   = aws_iam_role.states.id
  policy = data.aws_iam_policy_document.states.json
}

resource "aws_sfn_state_machine" "pipeline" {
  name       = "${var.name}-pipeline"
  role_arn   = aws_iam_role.states.arn
  definition = jsonencode(local.definition)
}

# --- Triggers --------------------------------------------------------------------------------

data "aws_iam_policy_document" "events_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "events" {
  statement {
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.pipeline.arn]
  }
}

resource "aws_iam_role" "events" {
  name               = "${var.name}-start-pipeline"
  assume_role_policy = data.aws_iam_policy_document.events_assume.json
}

resource "aws_iam_role_policy" "events" {
  name   = "start-pipeline"
  role   = aws_iam_role.events.id
  policy = data.aws_iam_policy_document.events.json
}

resource "aws_cloudwatch_event_rule" "weekly" {
  name                = "${var.name}-sarb-weekly"
  schedule_expression = var.schedule
}

resource "aws_cloudwatch_event_target" "weekly" {
  rule     = aws_cloudwatch_event_rule.weekly.name
  arn      = aws_sfn_state_machine.pipeline.arn
  role_arn = aws_iam_role.events.arn
  input    = jsonencode({ source = "sarb" })
}

# A workbook uploaded to landing starts a run. The bucket must send its events to EventBridge.
resource "aws_cloudwatch_event_rule" "upload" {
  name = "${var.name}-retail-upload"
  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created"]
    detail = {
      bucket = { name = [var.bucket_name] }
      object = { key = [{ wildcard = "landing/stats_sa/*.xlsx" }] }
    }
  })
}

resource "aws_cloudwatch_event_target" "upload" {
  rule     = aws_cloudwatch_event_rule.upload.name
  arn      = aws_sfn_state_machine.pipeline.arn
  role_arn = aws_iam_role.events.arn

  input_transformer {
    input_paths = {
      bucket = "$.detail.bucket.name"
      key    = "$.detail.object.key"
    }
    input_template = "{\"source\": \"retail\", \"bucket\": \"<bucket>\", \"key\": \"<key>\"}"
  }
}

output "state_machine_arn" { value = aws_sfn_state_machine.pipeline.arn }
output "definition" { value = local.definition }
output "upload_pattern" { value = jsondecode(aws_cloudwatch_event_rule.upload.event_pattern) }
