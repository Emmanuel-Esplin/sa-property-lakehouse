#!/usr/bin/env bash
# Run the whole pipeline once on AWS: SARB into bronze, Spark, then dbt. Waits, and fails if it fails.
# force=true runs Spark and dbt even when SARB has nothing new.
set -euo pipefail

state_machine="$1"
arn=$(aws stepfunctions start-execution --state-machine-arn "$state_machine" \
  --input '{"source": "sarb", "force": true}' --query executionArn --output text)
echo "started ${arn##*:}"
while true; do
  status=$(aws stepfunctions describe-execution --execution-arn "$arn" --query status --output text)
  [ "$status" != "RUNNING" ] && break
  sleep 15
done
aws stepfunctions describe-execution --execution-arn "$arn" \
  --query '{status:status,started:startDate,stopped:stopDate,error:error,cause:cause}' --output json
[ "$status" = "SUCCEEDED" ]
