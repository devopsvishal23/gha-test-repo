# Rebrush Runbook — resume this project from a cold start

**Fast path (added 2026-09-20):** `./scripts/resume.sh` and `./scripts/teardown.sh` automate all
of Phase B's check-and-resume / pause steps below (RDS start/stop, ALB recreate/delete, ECS scale
up/down) — idempotent, safe to re-run. Use these day-to-day; the manual commands below are for
understanding what the scripts do, or for when something doesn't match what the script expects
(e.g. a resource genuinely deleted, not just paused).

Run these top to bottom, in order, next time you come back to this project after a gap. Each
command has a **Why** (what it's for) and a **Flags** line (what each flag/option means) so you
don't need to remember AWS CLI syntax from scratch. This is a living doc — keep appending as new
phases/steps get added to the rebrush.

General flags you'll see everywhere:
- `--region us-east-2` — every resource here lives in this region; the CLI won't guess it for you.
- `--no-cli-pager` — without this, the AWS CLI pipes long output into `less`, which looks "stuck"
  until you press `q`. This flag prints straight to the terminal instead.
- `--query '...'` — a JMESPath filter that picks out just the fields you care about from a much
  bigger JSON response, so you're not scanning a huge blob for one value.
- `--output text` / `--output json` / `--output table` — how the filtered result is printed.

---

## Phase A — Docker sanity check

**Why:** confirm the app still runs locally before touching anything in AWS. Cheap, fast, catches
local environment drift (Docker Desktop updates, stale images) early.

```bash
docker compose up -d
```
**Flags:** `up` builds/starts everything in `docker-compose.yml`; `-d` runs it in the background
instead of blocking your terminal.

```bash
docker compose ps
```
**Why:** confirms both `web` and `db` are `Up`/`healthy` before you bother opening a browser.

Then check `http://localhost:5000/` loads and `admin`/`admin` logs in.

```bash
docker compose down
```
**Why:** stop the local containers once you've confirmed the basics work — no need to leave them
running while you move on to AWS. **No `-v`** — that would also delete the local `pgdata` volume,
which you don't want on a routine check (only do that deliberately if you want to re-test the
"data survives a restart" lesson from scratch).

---

## Phase B — Check & resume AWS infra

**Why this whole phase exists:** resources here are usually not deleted between sessions — they're
*paused* to save cost (see `COST-SAVING.md`). So on a rebrush, the default assumption should be
"check first, only recreate what's actually missing" — don't rebuild blind.

### B1 — Security groups (should always still exist — SGs aren't part of the cost-pause routine)

```bash
aws ec2 describe-security-groups --region us-east-2 --no-cli-pager \
  --filters "Name=group-name,Values=gha-test-repo-alb-sg,gha-test-repo-app-sg,gha-test-repo-db-sg" \
  --query 'SecurityGroups[*].{Name:GroupName,ID:GroupId,VpcId:VpcId,Inbound:IpPermissions}' \
  --output json
```
**Flags:** `--filters "Name=group-name,Values=..."` — server-side filter so AWS only returns
these 3 groups instead of every SG in the account.

**What to check in the output:** `gha-test-repo-alb-sg` allows 80+443 from `0.0.0.0/0`;
`gha-test-repo-app-sg` allows 5000 only from the alb-sg's `GroupId` (not a CIDR); `gha-test-repo-db-sg`
allows 5432 only from the app-sg's `GroupId`. If any rule uses a CIDR where it should use a
`GroupId`, that's drift — fix it before moving on.

Known IDs (from the 2026-08/09 rebrush — re-verify VpcId matches, don't assume it never changes):
- VPC: `vpc-0f3bf3667d5fedbd0`
- alb-sg: `sg-02ea60b03f77b121f`
- app-sg: `sg-0ca570b4815b60a55`
- db-sg: `sg-0498d9a1af0f3d92e`

### B2 — RDS

```bash
aws rds describe-db-instances --region us-east-2 --db-instance-identifier gha-test-repo-db \
  --no-cli-pager \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Endpoint:Endpoint.Address,DBName:DBName,PubliclyAccessible:PubliclyAccessible,SGs:VpcSecurityGroups}'
```
**Why check `PubliclyAccessible`:** it must be `false` — this DB should never be reachable from
the internet directly, only from the app via `db-sg`.

If `Status` is `stopped` (expected — this is the normal cost-saving pause state):
```bash
aws rds start-db-instance --region us-east-2 --db-instance-identifier gha-test-repo-db
```

Poll until it flips to `available` — **do not proceed to starting ECS until it does**, or tasks
will fail health checks against an unreachable DB:
```bash
aws rds describe-db-instances --region us-east-2 --db-instance-identifier gha-test-repo-db \
  --no-cli-pager --query 'DBInstances[0].DBInstanceStatus' --output text
```

If this command errors `DBInstanceNotFound` instead — the instance is actually gone, not paused,
and needs to be recreated from scratch (see `DEVOPS-JOURNEY.md` step log for the original
creation steps).

### B3 — ECS service

```bash
aws ecs describe-services --region us-east-2 --cluster gha-test-repo-cluster --services gha-test-repo-service \
  --no-cli-pager --query 'services[0].{Status:status,Desired:desiredCount,Running:runningCount,TaskDef:taskDefinition}'
```
**Why:** confirms the cluster/service/task-definition trio survived (they're free to leave idle —
only *running* tasks cost anything) and tells you the current desired count.

If `Desired` is `0` (expected — paused) and RDS is now `available`, scale back up:
```bash
aws ecs update-service --region us-east-2 --cluster gha-test-repo-cluster --service gha-test-repo-service --desired-count 2
```
**Flags:** `--desired-count 2` — matches the original steady-state of 2 tasks behind the ALB.

### B4 — ECR image

```bash
aws ecr describe-images --region us-east-2 --repository-name gha-test-repo-app \
  --no-cli-pager --query 'imageDetails[*].imageTags' --output json
```
**Why:** confirms the last-deployed image is still in the registry (ECR storage isn't part of the
cost-pause routine, so this should basically always be there — it's a cheap confirmation, not a
resume action).

### B5 — ALB (the one piece that's usually actually deleted, not paused)

```bash
aws elbv2 describe-load-balancers --region us-east-2 --names gha-test-repo-alb \
  --no-cli-pager --query 'LoadBalancers[0].{DNS:DNSName,State:State.Code,SGs:SecurityGroups}'
```

If this errors `LoadBalancerNotFound`, it was deleted for cost (per `COST-SAVING.md` — ALBs bill
hourly just for existing, no stop/start option) and needs recreating — `scripts/resume.sh` does
this automatically, including both listeners (see Phase E below).

**Manual step every time, since Phase E (2026-09-21) — not automated on purpose:**
`nixverse.skyonix.in`'s CNAME (at the external registrar, not Route 53 — deliberately not using
Route 53 for this domain for now) must be updated to point at the new ALB DNS name after every
recreate. `resume.sh` prints the new DNS name at the end specifically so you have it ready to
paste into the registrar's panel.

---

## Phase C — CI/CD

**Why:** confirm the pipeline still deploys correctly rather than assuming it does.

```bash
gh run list --limit 10
```
**Why:** shows recent run history/status — all green with no recent failures is a good sign
nothing's drifted.

```bash
git log -1 --format='%H %ad %s' -- .github/workflows/flask-postgres.yml
```
**Why:** confirms the workflow file itself hasn't been silently edited since you last verified it
— compare the commit hash/date against what you remember.

See `GITHUB-ACTIONS-CONCEPTS.md` for the full concept walkthrough of this workflow file if any of
it needs re-explaining.

## Phase D — prove the pipeline live

Not something you re-run every rebrush — this was a one-time proof (added a `GIT_SHA` build-arg
displayed in the UI footer) that a real code change flows end-to-end through CI/CD. Worth
repeating informally any time you're unsure the pipeline still actually deploys, by pushing any
small, safe change and watching `gh run watch`.

## Phase E — HTTPS / ACM

**Why:** unlike RDS/ECS/SGs, the ACM certificate is **not** part of the pause/resume cycle — it
was found fully deleted (not paused) when this phase was resumed on 2026-09-21, unlike everything
else in Phase B. Certs also don't attach to the target group (which survives ALB deletion) — they
attach to a *listener*, which belongs to the ALB and dies with it. So HTTPS needs re-verifying
independently of the Phase B check-list above.

```bash
aws acm list-certificates --region us-east-2 --no-cli-pager \
  --query 'CertificateSummaryList[*].{Domain:DomainName,ARN:CertificateArn,Status:Status}'
```
**Why:** if this is empty, the cert is gone and needs a full re-request + DNS validation (see
`INTERVIEW-QA.md` for the registrar-vs-Route-53 delegation gotchas hit doing this the first time).
If it lists `nixverse.skyonix.in` as `ISSUED`, the cert survived — only the ALB's listener
(destroyed with the ALB) needs recreating, which `scripts/resume.sh` now does automatically using
the hardcoded `CERT_ARN` in that script. **If the cert was re-requested with a new ARN, update
`CERT_ARN` in `scripts/resume.sh` to match**, or the script's HTTPS listener creation will fail
referencing a dead certificate.

```bash
aws elbv2 describe-listeners --region us-east-2 --load-balancer-arn $(aws elbv2 describe-load-balancers --region us-east-2 --names gha-test-repo-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text) \
  --no-cli-pager --query 'Listeners[*].{Port:Port,Protocol:Protocol}'
```
**Why:** should show both `443/HTTPS` and `80/HTTP` (the latter redirecting to HTTPS, not
forwarding — check via `describe-listeners` with `--query 'Listeners[*].DefaultActions'` if
unsure). `scripts/resume.sh` creates both automatically now.

---

## (Phase F gets appended here once the current rebrush reaches it)
