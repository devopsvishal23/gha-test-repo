# Rebrush Plan — full hands-on rebuild from scratch

**Status: NOT STARTED.** Created 2026-08-19, saved so a new session (after a VS Code restart or
any gap) can resume exactly here without re-deriving context.

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
