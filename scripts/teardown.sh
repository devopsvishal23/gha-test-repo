#!/usr/bin/env bash
# Pause the pausable resources between practice sessions (does NOT delete RDS/ECS/SGs/ECR — see
# REBRUSH-RUNBOOK.md for why only the ALB actually gets deleted here). Safe to re-run.
set -euo pipefail

REGION="us-east-2"
CLUSTER="gha-test-repo-cluster"
SERVICE="gha-test-repo-service"
RDS_ID="gha-test-repo-db"
ALB_NAME="gha-test-repo-alb"

echo "== Scaling ECS service to 0 =="
aws ecs update-service --region "$REGION" --cluster "$CLUSTER" --service "$SERVICE" \
  --desired-count 0 --no-cli-pager --query 'service.{Desired:desiredCount}'

echo "== Stopping RDS (skipped if already stopped) =="
RDS_STATUS=$(aws rds describe-db-instances --region "$REGION" --db-instance-identifier "$RDS_ID" \
  --no-cli-pager --query 'DBInstances[0].DBInstanceStatus' --output text)
if [ "$RDS_STATUS" = "available" ]; then
  aws rds stop-db-instance --region "$REGION" --db-instance-identifier "$RDS_ID" --no-cli-pager >/dev/null
  echo "RDS stop requested (was: available)"
else
  echo "RDS already in state '$RDS_STATUS' — skipping stop"
fi

echo "== Deleting ALB (skipped if already gone) =="
ALB_ARN=$(aws elbv2 describe-load-balancers --region "$REGION" --names "$ALB_NAME" \
  --no-cli-pager --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null || echo "NONE")
if [ "$ALB_ARN" != "NONE" ]; then
  aws elbv2 delete-load-balancer --region "$REGION" --load-balancer-arn "$ALB_ARN" --no-cli-pager
  echo "ALB delete requested ($ALB_ARN)"
else
  echo "No ALB found — skipping"
fi

echo "== Done. RDS/ECS/SGs/ECR/target group are untouched — see resume.sh to bring it all back. =="
