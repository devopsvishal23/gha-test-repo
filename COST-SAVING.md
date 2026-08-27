# Cost Saving — Pausing / Resuming AWS Resources When Not Actively Working

Quick reference for shutting things down between sessions (or overnight) and bringing them back
up, without tearing down the whole stack. All commands assume region `us-east-2`, account
`793110104712`. Fill in placeholders (`<...>`) with fresh values where noted — some change every
time a resource is recreated.

## Why each resource is handled differently

| Resource | Can it be "paused"? | What actually saves money |
|---|---|---|
| RDS | Yes — native stop/start | `stop-db-instance` (auto-restarts after 7 days if left stopped) |
| ECS (Fargate) | Yes — scale to 0 | Only running tasks are billed; cluster/service/task def are free when idle |
| ALB | **No** — always billed hourly + LCU while it exists | Only real saving is delete + recreate |
| ECR image storage | N/A | A few cents/GB-month — not worth touching |
| Secrets Manager | N/A | ~$0.40/month per secret — not worth touching |

---

## RDS

**Stop** (data preserved, auto-restarts after 7 days if left stopped that long):
```bash
aws rds stop-db-instance --region us-east-2 --db-instance-identifier gha-test-repo-db
```

**Start**:
```bash
aws rds start-db-instance --region us-east-2 --db-instance-identifier gha-test-repo-db
```

**Check status**:
```bash
aws rds describe-db-instances --region us-east-2 --db-instance-identifier gha-test-repo-db --query 'DBInstances[0].DBInstanceStatus' --output text
```

---

## ECS (Fargate service)

**Stop** (scales running tasks to 0 — cluster, service, task definition all stay intact):
```bash
aws ecs update-service --region us-east-2 --cluster gha-test-repo-cluster --service gha-test-repo-service --desired-count 0
```

**Start** (back to normal 2-task steady state):
```bash
aws ecs update-service --region us-east-2 --cluster gha-test-repo-cluster --service gha-test-repo-service --desired-count 2
```

**Check status**:
```bash
aws ecs describe-services --region us-east-2 --cluster gha-test-repo-cluster --services gha-test-repo-service --query 'services[0].{Desired:desiredCount,Running:runningCount}' --output json
```

---

## ALB — no pause, only delete/recreate

ALBs bill hourly the moment they exist, whether or not they're serving traffic — there's no
stop/start. To actually save the ~$16-20/month baseline (plus LCU usage), delete it when you're
done for a stretch, recreate it when you resume. **The target group survives this** (it's a
separate resource, unaffected by deleting the ALB), so the ECS service doesn't need any changes —
only the ALB + its listener get recreated.

**Caveat**: every time you recreate the ALB, it gets a **new DNS name** — the old
`gha-test-repo-alb-<id>.us-east-2.elb.amazonaws.com` is gone for good. If/when HTTPS + a real
domain CNAME is added later (Phase E), that CNAME record will need updating too after every
recreate.

**Delete**:
```bash
aws elbv2 describe-load-balancers --region us-east-2 --names gha-test-repo-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text
```
```bash
aws elbv2 delete-load-balancer --region us-east-2 --load-balancer-arn <PASTE_ALB_ARN_FROM_ABOVE>
```

**Recreate** (same subnets/SG as the original setup):
```bash
aws elbv2 create-load-balancer --region us-east-2 --name gha-test-repo-alb \
  --subnets subnet-08b83cddde742d501 subnet-09b8fcd0faad20fba subnet-0a2feed5036e15d27 \
  --security-groups sg-02ea60b03f77b121f \
  --scheme internet-facing --type application \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text
```

Then re-attach the listener, forwarding to the **existing** target group (its ARN doesn't
change):
```bash
aws elbv2 create-listener --region us-east-2 --load-balancer-arn <NEW_ALB_ARN_FROM_ABOVE> \
  --protocol HTTP --port 80 \
  --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:us-east-2:793110104712:targetgroup/gha-test-repo-tg/cb2554c4799242e7
```

**Get the new DNS name**:
```bash
aws elbv2 describe-load-balancers --region us-east-2 --names gha-test-repo-alb --query 'LoadBalancers[0].DNSName' --output text
```

Give it a minute, then re-check target health (targets should already be registered against the
surviving target group — just confirm they're `healthy` again once the new ALB is up):
```bash
aws elbv2 describe-target-health --region us-east-2 --target-group-arn arn:aws:elasticloadbalancing:us-east-2:793110104712:targetgroup/gha-test-repo-tg/cb2554c4799242e7 --query 'TargetHealthDescriptions[*].TargetHealth' --output json
```

---

## Full "end of session" shutdown (RDS + ECS only — ALB left as a judgment call)

```bash
aws rds stop-db-instance --region us-east-2 --db-instance-identifier gha-test-repo-db
aws ecs update-service --region us-east-2 --cluster gha-test-repo-cluster --service gha-test-repo-service --desired-count 0
```

Add the ALB delete step too if you know it'll be more than a day or two before the next session.

## Full "resume session" startup

```bash
aws rds start-db-instance --region us-east-2 --db-instance-identifier gha-test-repo-db
aws ecs update-service --region us-east-2 --cluster gha-test-repo-cluster --service gha-test-repo-service --desired-count 2
```

Wait for RDS to show `available` before scaling ECS back up (tasks will fail health checks and
the deployment circuit breaker may trip if the DB isn't reachable yet — see `INTERVIEW-QA.md` for
why). Re-run the ALB recreate steps above if it was deleted.
