# DevOps Journey — gha-test-repo

A running log of taking this Flask + Postgres app from "Dockerfile on a laptop" to a real
production deployment on AWS, one step at a time. Keep this file updated as we go so a new
session (or a new person) can pick up without re-deriving everything.

## Architecture (current state)

```
GitHub (push to main)
   |
   v
GitHub Actions (.github/workflows/flask-postgres.yml)
   |  build image --> push to ECR --> force new ECS deployment
   v
ECR repo: gha-test-repo-app (tag: latest)
   |
   v
ECS Cluster: gha-test-repo-cluster (Fargate)
   `-- Service: gha-test-repo-service
         `-- Task Definition: gha-test-repo-task (container: flask-app, port 5000)
               `-- env: DB_HOST / DB_NAME / DB_USER / DB_PASSWORD (plaintext - see Known Gaps)
               `-- env: SECRET_KEY / ADMIN_USERNAME / ADMIN_PASSWORD (see Environment variables reference)
   |
   v
Application Load Balancer: gha-test-repo-alb (HTTP :80 only)
   `-- Target group: gha-test-repo-tg (health check: /health)
   |
   v
RDS PostgreSQL: gha-test-repo-db
   endpoint: gha-test-repo-db.cpqua8q6gm9u.us-east-2.rds.amazonaws.com
   db name: testdb, not publicly accessible

Security groups:
  gha-test-repo-alb-sg  -> inbound 80 from 0.0.0.0/0 (attached to the ALB)
  gha-test-repo-app-sg  -> inbound 5000 from gha-test-repo-alb-sg only (attached to ECS tasks)
  gha-test-repo-db-sg   -> inbound 5432 from gha-test-repo-app-sg only
```

## Steps completed so far

1. **Diagnosed local docker-compose failure** — port 5432 conflicted with an unrelated project's
   Postgres container already running on the host. Fixed by remapping to `5433:5432` in
   `docker-compose.yml` (host-only change, doesn't affect the built image).
2. **Verified Postgres data persistence** — confirmed the named volume `pgdata` survives
   `docker compose down` / `up` (data only lost on `down -v` or manual volume removal).
3. **Created RDS Postgres instance** (`gha-test-repo-db`) via AWS Console — Free tier template,
   not publicly accessible, initial DB name `testdb` (matches app's expected `DB_NAME`).
4. **Networking**: created `gha-test-repo-app-sg` security group and added an inbound rule on
   `gha-test-repo-db-sg` allowing Postgres traffic from `gha-test-repo-app-sg` (not from 0.0.0.0/0).
5. **Created ECS Cluster** `gha-test-repo-cluster` (Fargate, serverless — no EC2 instances to manage).
6. **Created a dedicated ECR repo** `gha-test-repo-app` (replacing an older repo
   `cloudops-flaskpostgres-cont` used in earlier pipeline experiments — now unused).
7. **Updated CI/CD** (`flask-postgres.yml`) to push images to the new ECR repo.
8. **Created ECS Task Definition** `gha-test-repo-task` — container `flask-app`, image from ECR,
   port 5000, DB connection env vars pointing at the RDS endpoint.
9. **Created ECS Service + Application Load Balancer** in one step via the ECS console wizard —
   `gha-test-repo-service` behind `gha-test-repo-alb`, target group health-checked on `/health`.
10. **Verified live**: app reachable at `http://gha-test-repo-alb-337751091.us-east-2.elb.amazonaws.com/`,
    confirmed the RDS connection works end-to-end (added a row via `/add`, saw it persist).
11. **Wired auto-deploy**: added a `Force new ECS deployment` step to the `deploy` job in
    `flask-postgres.yml`, running `aws ecs update-service --force-new-deployment` after every image
    push. Verified: a push to `main` triggered a real ECS rollout (`PRIMARY` deployment,
    `rolloutState: COMPLETED`).
12. **Added minimal login** (`flask-login`, single seeded admin user in a new `users` Postgres
    table, `@login_required` on `/`, `/add`, `/delete/<id>`, `/health` left open for the ALB health
    check) plus a motivational-quote banner that rotates every 15 minutes (deterministic
    time-bucket pick from a 36-quote list — no scheduler/cron needed). Also turned off Flask
    `debug=True` in `app.py` now that real credentials exist (it was exposing a live Werkzeug
    debugger PIN in logs — a shell-access risk). Registered a new Task Definition revision
    (`gha-test-repo-task:2`) with the three new env vars below and updated the service to use it.
    - *Scope decision*: chose "minimal" (single seeded admin, no self-service registration) over
      "full" (public `/register` page, per-user validation) — minimal was estimated at ~30-45 min
      to write + ~15-20 min to test/redeploy vs ~1.5-2 hrs for full; picked minimal since the goal
      here is learning the deploy mechanics of shipping an auth change, not building a real
      multi-user product yet.

    - *Verified live in production* on 2026-08-02: `http://gha-test-repo-alb-337751091.us-east-2.elb.amazonaws.com/`
      now returns `302 -> /login` for unauthenticated requests, confirming the rolled-out task is
      running `gha-test-repo-task:2` with the new auth code.

**Current state: fully automated deploy loop from `git push` to live traffic, working, with basic auth in front of the app.**

## Environment variables reference

| Var | Consumed by | Purpose |
|---|---|---|
| `DB_HOST`/`DB_NAME`/`DB_USER`/`DB_PASSWORD` | `DB_CONFIG` in `app.py`, every request that touches Postgres | RDS connection info |
| `SECRET_KEY` | `app.secret_key` (`app.py:15`) — Flask's session/cookie signer | Signs the login-session cookie so it can't be forged client-side. Rotating it logs everyone out (old cookies stop verifying). Must be a real random value in production (`openssl rand -hex 32`) — never the dev fallback. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `seed_admin()` (`app.py:111-113`), run once at container startup only | Bootstraps one admin row in the `users` table if it doesn't exist yet (password is hashed before storage, never kept in plaintext). **Known limitation**: since it only acts when the username is missing, changing `ADMIN_PASSWORD` later and redeploying will NOT rotate an existing admin's password — that needs a direct DB update or a future admin UI. |

## Deployment behavior / downtime

Checked the live config rather than assuming — current settings on `gha-test-repo-service`:

- Rolling deployment, `minimumHealthyPercent: 100`, `maximumPercent: 200` — ECS always boots the
  new task and waits for it to pass health checks *before* touching the old one.
- Deployment circuit breaker enabled with automatic rollback — a new task that never becomes
  healthy triggers an automatic revert to the previous working version, no manual step needed.
- ALB target group health check: every 30s, 5 consecutive passes required — a new task takes
  roughly **2.5–3 minutes** after boot before it's marked healthy and starts receiving traffic.
- ALB deregistration delay: 300s — once the new task is healthy, the old one stops receiving *new*
  requests immediately but gets up to 5 minutes to finish in-flight ones before ECS kills it.

**Net effect: deploys are already zero-downtime by design** — there's never a moment where the
running healthy task count drops to zero.

**The actual resilience gap is `desiredCount: 1`** — only one task ever runs. That's fine for
planned deploys (covered above), but an *unplanned* crash of that single task (OOM, unhandled
exception, AZ issue) causes real downtime until ECS notices and replaces it. Raising
`desiredCount` to 2 would close this gap too, roughly doubling compute cost. Tracked as a roadmap
item below rather than done now.

## Known gaps / roadmap ahead

Not urgent, but real production-hygiene items to tackle next, roughly in this order:

1. **`DB_PASSWORD` is a plaintext environment variable** in the Task Definition — move it to
   AWS Secrets Manager and reference it as a secret instead.
2. **No HTTPS** — the ALB only has an HTTP :80 listener. Add an ACM certificate + 443 listener.
3. **Mutable `:latest` image tag** — every deploy overwrites the same tag, so there's no clean way
   to know exactly what's running or roll back to a specific past build. Move to immutable
   git-SHA tags with a new Task Definition revision registered per deploy.
4. ~~**`gha-test-repo-app-sg` allows inbound 5000 from `0.0.0.0/0`** — should be tightened to only
   accept traffic from the ALB's security group~~ — fixed 2026-08-03. Backstory: the ECS console
   wizard originally attached `gha-test-repo-app-sg` to *both* the ALB and the ECS tasks (a single
   SG doing double duty), which only had port 5000 open — so the ALB itself was rejecting all
   port-80 traffic and the app didn't work until a manual `0.0.0.0/0:80` rule was added directly to
   that SG as a quick unblock. Properly fixed by creating a dedicated `gha-test-repo-alb-sg`
   (inbound 80 from `0.0.0.0/0`), attaching it to the ALB, and locking `gha-test-repo-app-sg` down to
   only accept port 5000 from `gha-test-repo-alb-sg`. Verified via `aws ec2 describe-security-groups`
   — confirmed on both SGs.
5. ~~**`desiredCount: 1`** — no redundancy against an unplanned task crash (see Deployment behavior
   above). Raise to 2+ for real resilience, not just deploy safety.~~ — fixed 2026-08-03, raised to
   2. Verified via `aws ecs describe-services`: `desiredCount: 2`, `runningCount: 2`.
6. Not yet discussed, natural next topics: autoscaling policies, CloudWatch alarms/monitoring,
   replacing manual console clicks with Terraform (IaC).
7. ~~`Dockerfile.multistage` in the repo root is unused by this pipeline and has a stale
   `EXPOSE 8000` (app actually listens on 5000)~~ — fixed 2026-08-03, now `EXPOSE 5000`.
   Still unused by the CI/CD pipeline (which builds from the plain `dockerfile`).
8. **Admin password rotation isn't wired up** — `seed_admin()` only creates the admin user if
   missing; changing `ADMIN_PASSWORD` and redeploying won't update an existing admin's password
   (see Environment variables reference above).
