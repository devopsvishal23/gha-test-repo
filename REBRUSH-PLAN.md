# Rebrush Plan — full hands-on rebuild from scratch

**Status: IN PROGRESS — Phases A and B complete as of 2026-08-27.** Created 2026-08-19, saved so
a new session (after a VS Code restart or any gap) can resume exactly here without re-deriving
context. JD-HANDS-ON-PLAN.md is shelved until this whole rebrush (steps 1-17) closes — pacing
decision made 2026-08-24/27: bundle sub-clicks per step like the original build did, skip
re-hitting bugs already fixed once (see below), full explanations otherwise, targeting ~1 week
total.

**Live right now**: `http://gha-test-repo-alb-419297987.us-east-2.elb.amazonaws.com/` — RDS,
all 3 SGs, ECS cluster, ECR repo (`gha-test-repo-app`, git-SHA tag
`99d210740729bf94387babfc7d30e265eadd0024`), Secrets Manager secret
(`gha-test-repo/db-password`, new ARN suffix `-YwdOtQ` — old `-FacJCs` was stale, IAM policy
already corrected), Task Definition `gha-test-repo-task:7`, ECS service (2/2 running, targets
healthy), ALB all up and verified end-to-end (login + `/add` working). **Note: this new ALB DNS
name differs from the original** (`...-337751091...` before teardown vs `...-419297987...` now).

**New gotchas hit during this rebuild** (beyond the ones from the original build, see
`INTERVIEW-QA.md` for full writeups):
- IAM roles and the CI/CD workflow file survived the 2026-08-17 teardown (only RDS/ECS/ALB/SGs/
  ECR/Secrets/ACM were deleted) — `ecsTaskExecutionRole` and `.github/workflows/flask-postgres.yml`
  already existed/were already at their final hardened state, so Secrets Manager was pulled
  forward earlier in the rebuild order than day-1 did it, to avoid redoing the Task Definition
  twice.
- A leftover `CREATE_COMPLETE` CloudFormation stack from the original 2026-08-02 service creation
  (`ECS-Console-V2-Service-...`) was never cleaned up by the teardown and blocked recreating the
  service under the same name — had to be deleted manually first.
- Bootstrap image built locally on Apple Silicon lacked a `linux/amd64` manifest variant —
  Fargate couldn't pull it. Rebuilt with `docker buildx build --platform linux/amd64`.
- **The ALB-vs-app security-group mixup from the original build (see `INTERVIEW-QA.md`) recurred
  even after explicitly selecting the correct SGs in the wizard** — the load balancer's SG field
  and the service's network-config SG field are independent and can each default wrong separately.
  Always verify both with the CLI after using the combined create-service-and-ALB wizard.

## Why this exists

User was away for ~10-12 days and lost context on where the project stood. Rather than a passive
re-read of `DEVOPS-JOURNEY.md`/`TERRAFORM-JOURNEY.md`, the plan is to redo the entire build
hands-on, step by step, as a real refresher — timed well, since the full production stack
(ECS, ALB, RDS, security groups, ECR, Secrets Manager, ACM cert) was deliberately torn down on
2026-08-17 (unrelated request, see `DEVOPS-JOURNEY.md` teardown entry). There is currently
**nothing live in AWS for this app** — the rebuild is a real deployment, not a simulated drill.

## Open question before starting (ask the user first)

Single long hands-on session for Phases A-E, or paced across multiple sessions (stop after each
phase, resume next time)? Not yet answered — ask before beginning Phase A.

## Phases (mapped to DEVOPS-JOURNEY.md's own step log, steps 1-17)

**Phase A — Docker fundamentals** (steps 1-2)
Local `docker-compose` up, the port-5432-conflict fix, why the named `pgdata` volume survives
`down` but not `down -v`. Quick warm-up before touching AWS.

**Phase B — Core AWS infra, rebuilt by hand** (steps 3-10)
RDS instance -> security groups (`db-sg` only trusts `app-sg`, never `0.0.0.0/0`) -> ECS cluster
(Fargate) -> ECR repo -> Task Definition -> ECS Service + ALB. The backbone; verify each step
against real AWS state before moving to the next.

**Phase C — Wire up CI/CD** (step 11)
`git push` -> GitHub Actions -> force a new ECS deployment. First full loop closes.

**Phase D — Ship a real feature through the pipeline** (step 12)
Re-add the login/auth layer (or equivalent) to prove a code change can go end-to-end through the
pipeline just built, not just the initial deploy.

**Phase E — Production hardening** (steps 13-17)
Secrets Manager for `DB_PASSWORD`, ACM + HTTPS on the ALB (the DNS/registrar gotchas from
`DEVOPS-JOURNEY.md` step 14 are worth hitting again deliberately), path-filtered CI triggers,
immutable git-SHA task definitions, admin password rotation.

**Phase F — Terraform, done right this time**
Same import-based approach as `TERRAFORM-JOURNEY.md`, but write the `.tf` file *before* creating
each resource in Phases B-E instead of importing after the fact, so Terraform is the source of
truth from day one instead of a retrofit. Naturally re-covers state/backend/locking concepts.
Note: `terraform/` in this repo currently only has the default VPC + subnets left in state (the
three security groups were destroyed along with the rest of the stack on 2026-08-17) — Phase F
starts from that, not from zero.

## Format (per [[feedback_devops_learning_style]] in memory)

- Ask a "why" checkpoint before each phase starts.
- User builds it hands-on (console clicks or CLI commands handed over, not run by me) —
  standing preference, see memory.
- Verify against real AWS state before moving to the next phase.
- Don't slow down re-explaining anything the user clearly still knows — this is a rebrush, not a
  re-teach.
- Timestamp start/completion per step per the existing standing instruction, once work resumes.

## Resume instructions for next session

1. Confirm the open pacing question above.
2. Re-check current AWS state before assuming anything (things may have changed since
   2026-08-19) — `aws rds describe-db-instances`, `aws ecs list-clusters`, etc. in `us-east-2`.
3. Start Phase A.
