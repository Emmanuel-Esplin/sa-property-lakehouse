#!/usr/bin/env bash
# Start a Glue job, wait for it, and fail if it does not succeed.
set -euo pipefail

job="$1"
run_id=$(aws glue start-job-run --job-name "$job" --query JobRunId --output text)
echo "$job: started $run_id"
while true; do
  state=$(aws glue get-job-run --job-name "$job" --run-id "$run_id" \
    --query JobRun.JobRunState --output text)
  case "$state" in
    SUCCEEDED | FAILED | STOPPED | TIMEOUT | ERROR | EXPIRED) break ;;
  esac
  sleep 10
done
aws glue get-job-run --job-name "$job" --run-id "$run_id" \
  --query 'JobRun.{state:JobRunState,seconds:ExecutionTime,dpuSeconds:DPUSeconds,error:ErrorMessage}' \
  --output json
[ "$state" = "SUCCEEDED" ]
