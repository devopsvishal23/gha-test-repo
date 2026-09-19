#!/usr/bin/env bash
# Reverse of teardown.sh — brings RDS/ALB/ECS back up for a practice session. Safe to re-run.
set -euo pipefail

REGION="us-east-2"
CLUSTER="gha-test-repo-cluster"
SERVICE="gha-test-repo-service"
RDS_ID="gha-test-repo-db"
ALB_NAME="gha-test-repo-alb"
ALB_SG="sg-02ea60b03f77b121f"
SUBNETS="subnet-08b83cddde742d501 subnet-09b8fcd0faad20fba subnet-0a2feed5036e15d27"
TG_ARN="arn:aws:elasticloadbalancing:us-east-2:793110104712:targetgroup/gha-test-repo-tg/cb2554c4799242e7"

echo "== Starting RDS (skipped if already available) =="
RDS_STATUS=$(aws rds describe-db-instances --region "$REGION" --db-instance-identifier "$RDS_ID" \
  --no-cli-pager --query 'DBInstances[0].DBInstanceStatus' --output text)
if [ "$RDS_STATUS" = "stopped" ]; then
  aws rds start-db-instance --region "$REGION" --db-instance-identifier "$RDS_ID" --no-cli-pager >/dev/null
  echo "RDS start requested — waiting for 'available' (this is the slow part, ~3-5 min)..."
  while [ "$RDS_STATUS" != "available" ]; do
    sleep 15
    RDS_STATUS=$(aws rds describe-db-instances --region "$REGION" --db-instance-identifier "$RDS_ID" \
      --no-cli-pager --query 'DBInstances[0].DBInstanceStatus' --output text)
    echo "  RDS status: $RDS_STATUS"
  done
else
  echo "RDS already in state '$RDS_STATUS' — skipping start"
fi

echo "== Recreating ALB (skipped if it already exists) =="
ALB_ARN=$(aws elbv2 describe-load-balancers --region "$REGION" --names "$ALB_NAME" \
  --no-cli-pager --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null || echo "NONE")
if [ "$ALB_ARN" = "NONE" ]; then
  ALB_ARN=$(aws elbv2 create-load-balancer --region "$REGION" --name "$ALB_NAME" \
    --subnets $SUBNETS --security-groups "$ALB_SG" \
    --scheme internet-facing --type application \
    --no-cli-pager --query 'LoadBalancers[0].LoadBalancerArn' --output text)
  aws elbv2 create-listener --region "$REGION" --load-balancer-arn "$ALB_ARN" \
    --protocol HTTP --port 80 \
    --default-actions Type=forward,TargetGroupArn="$TG_ARN" \
    --no-cli-pager >/dev/null
  echo "ALB + listener created ($ALB_ARN)"
else
  echo "ALB already exists — skipping create"
fi

echo "== Scaling ECS service to 2 =="
aws ecs update-service --region "$REGION" --cluster "$CLUSTER" --service "$SERVICE" \
  --desired-count 2 --no-cli-pager --query 'service.{Desired:desiredCount}'

ALB_DNS=$(aws elbv2 describe-load-balancers --region "$REGION" --names "$ALB_NAME" \
  --no-cli-pager --query 'LoadBalancers[0].DNSName' --output text)
echo "== Done. Waiting ~1-2 min for tasks to pass health checks, then check: =="
echo "   http://$ALB_DNS/"
