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
   |  build image (tag: git SHA) --> push to ECR --> render + register new Task Definition
   |  revision pinned to that SHA --> deploy revision to ECS service, wait for stability
   v
ECR repo: gha-test-repo-app (tag: git SHA per deploy, no mutable :latest anymore)
   |
   v
ECS Cluster: gha-test-repo-cluster (Fargate)
   `-- Service: gha-test-repo-service
         `-- Task Definition: gha-test-repo-task (container: flask-app, port 5000)
               `-- image: pinned to the exact git-SHA tag of the commit that deployed it
               `-- env: DB_HOST / DB_NAME / DB_USER (plaintext)
               `-- secret: DB_PASSWORD (AWS Secrets Manager, see Environment variables reference)
               `-- env: SECRET_KEY / ADMIN_USERNAME / ADMIN_PASSWORD (see Environment variables reference)
   |
   v
Application Load Balancer: gha-test-repo-alb
   `-- Listener HTTPS :443 -> cert for nixverse.skyonix.in (ACM) -> forwards to gha-test-repo-tg
   `-- Listener HTTP  :80  -> 301 redirect to HTTPS :443 (same host/path/query)
   `-- Target group: gha-test-repo-tg (health check: /health)
   |
   v
DNS: nixverse.skyonix.in -> CNAME -> gha-test-repo-alb-337751091.us-east-2.elb.amazonaws.com
   (record lives at skyonix.in's actual registrar, NOT Route 53 - see step 14)
   |
   v
RDS PostgreSQL: gha-test-repo-db
   endpoint: gha-test-repo-db.cpqua8q6gm9u.us-east-2.rds.amazonaws.com
   db name: testdb, not publicly accessible

Security groups:
  gha-test-repo-alb-sg  -> inbound 80 and 443 from 0.0.0.0/0 (attached to the ALB)
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

13. **Moved `DB_PASSWORD` out of the Task Definition into AWS Secrets Manager** (2026-08-04),
    closing roadmap item 1 below:
    - Created secret `gha-test-repo/db-password` (plaintext string secret, no rotation configured
      yet) via the console, holding the RDS password.
    - Attached a scoped inline IAM policy to `ecsTaskExecutionRole` — `secretsmanager:GetSecretValue`
      restricted to exactly that secret's ARN, not a wildcard over all secrets.
    - *Concept: why ECS has an execution role and a task role, and why they're meant to be
      separate* — the **execution role** is used by the ECS agent itself (infrastructure layer)
      to start the container: pulling the image from ECR, writing logs to CloudWatch, and
      resolving any `secrets`/SSM parameters referenced in the task definition. The **task
      role** is what the *application code* uses at runtime if it calls AWS APIs directly (e.g.
      `boto3` calls to S3/SQS/etc). Keeping them separate limits blast radius: if the app code
      were ever compromised, it would only have the task role's narrow, app-specific permissions
      — not also whatever broader infrastructure access the execution role holds. In this repo
      both roles currently point at the same `ecsTaskExecutionRole` (harmless today since the
      Flask app doesn't call any AWS SDKs directly), but worth splitting them if that ever
      changes.
    - Registered Task Definition revision `gha-test-repo-task:3` — removed the plaintext
      `DB_PASSWORD` entry from `environment` and added a `secrets` array entry instead:
      `{"name": "DB_PASSWORD", "valueFrom": "<secret ARN>"}`. Every other env var (`DB_HOST`,
      `DB_NAME`, `DB_USER`, `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`) unchanged.
    - Updated `gha-test-repo-service` to revision `:3` with **Force new deployment**. Verified via
      `aws ecs describe-services`: single `PRIMARY` deployment, `rolloutState: COMPLETED`,
      `runningCount: 2` matching `desiredCount: 2`, `failedTasks: 0` (a permission gap here would
      have shown up as failed tasks unable to resolve the secret at launch).
    - *Verified live*: added a record via `/add`, hard-refreshed the browser, record still
      present — confirms both running tasks are reading the DB password from Secrets Manager
      correctly and writing to the same shared Postgres instance.

14. **Added HTTPS on the ALB** (2026-08-04) via ACM + a real domain, closing roadmap item 2
    below. Domain `skyonix.in`, subdomain `nixverse.skyonix.in`.
    - *Gotcha #1 — ACM region*: the certificate had to be requested in **us-east-2** (same
      region as the ALB), not `us-east-1` — that region rule is specific to CloudFront, not
      ALBs. Easy to mix up since both feel like "the ACM region for a load-balancing-ish thing."
    - *Gotcha #2 — Route 53 hosted zone existed but wasn't actually authoritative*: there was a
      Route 53 hosted zone for `skyonix.in` in this account, so the first attempt added the ACM
      DNS-validation CNAME there and used the "Create records in Route 53" auto-button. It sat at
      `PENDING_VALIDATION` for 8+ hours despite the record looking correct. Root cause: the
      domain is actually registered/DNS-hosted at a different provider, and that registrar's NS
      records were never pointed at this Route 53 hosted zone — so the zone was never
      authoritative, and nothing in it (including the validation record) was visible to the
      public internet, no matter how correct it looked in the AWS console. Diagnosed by comparing
      `dig NS skyonix.in` (what the internet sees) against the hosted zone's own
      `DelegationSet.NameServers` (what Route 53 thinks it should be) — they didn't match.
      Fix: added the validation CNAME directly at the actual registrar's DNS panel instead.
    - *Gotcha #3 — relative name vs. full FQDN in the registrar's DNS panel*: most registrar UIs
      want a record's Name/Host entered *relative to the zone* and auto-append the base domain —
      so pasting ACM's full validation name
      (`_hash.nixverse.skyonix.in.`) into that field silently created
      `_hash.nixverse.skyonix.in.skyonix.in.` (doubled suffix), which ACM never found. Fix: enter
      only `_hash.nixverse` (everything before `.skyonix.in`) as the Name/Host value. Diagnosed by
      `dig`-ing both the correct name and the doubled-suffix version to see which one actually
      resolved.
    - Once DNS was correct, validation was still stuck on the *original* certificate request
      (ACM has no manual "recheck now" action for DNS validation — it only polls on its own
      schedule). Deleted that request and issued a fresh one for the same domain
      (`aws acm request-certificate`) — new requests get validated faster since the DNS was
      already correct by then. New cert ARN ends in `...62535076-d7c5-4495-a8f8-1a5448395b19`,
      status `ISSUED`.
    - Added an **HTTPS :443 listener** on `gha-test-repo-alb` using the issued certificate,
      forwarding to `gha-test-repo-tg` (same target group as the HTTP listener used).
    - Changed the **HTTP :80 listener's** default action from `forward` to `redirect` — 301 to
      `https://#{host}/#{path}?#{query}` — so plain HTTP requests now bounce to HTTPS instead of
      being served unencrypted.
    - Added a **CNAME record at the actual registrar** (not Route 53, per Gotcha #2):
      `nixverse` -> `gha-test-repo-alb-337751091.us-east-2.elb.amazonaws.com`.
    - *Verified live*: `dig CNAME nixverse.skyonix.in` resolves to the ALB; `curl -I
      http://nixverse.skyonix.in/` returns `301` with a `Location: https://...` header; login and
      `/add` both confirmed working over `https://nixverse.skyonix.in/`.

15. **Scoped the CI/CD workflow to only run on relevant file changes** (2026-08-04). Previously
    `flask-postgres.yml` had no `paths` filter on its `push`/`pull_request` triggers, so *any*
    commit to `main` — including docs-only changes like the Secrets Manager/HTTPS writeups above
    — triggered a full rebuild, health-check run, and (on `main`) a real ECS redeployment. Wasteful
    but harmless, since the same image just got rebuilt and redeployed unchanged.
    - *Concept*: GitHub Actions supports `paths` (allowlist — only these paths trigger the
      workflow) and `paths-ignore` (blocklist — everything except these paths triggers it) on
      `push`/`pull_request` triggers. Chose **allowlist** here — safer for this repo, since any
      new non-code file added later (more docs, config, etc.) won't accidentally trigger a build
      unless someone remembers to exclude it. A blocklist only stays correct if you remember to
      keep adding to it.
    - Added `paths: [app.py, requirements.txt, dockerfile, docker-compose.yml, templates/**,
      .github/workflows/flask-postgres.yml]` to both the `push` and `pull_request` triggers —
      matches what the `build-and-test` and `deploy` jobs actually consume. Docs files
      (`*.md`) are deliberately not in the list.
    - *Forward-looking gotcha*: if branch protection is ever added requiring this workflow's
      checks to pass before merging, a path-filtered workflow that doesn't run (because a PR only
      touched docs) can leave that required check stuck "pending" forever, blocking the merge —
      GitHub doesn't auto-satisfy a required check that never ran. Not a problem today since there's
      no branch protection configured, but worth remembering if that changes.

16. **Replaced mutable `:latest` deploys with immutable git-SHA image tags + a real Task
    Definition revision per deploy** (2026-08-04), closing roadmap item 3 below:
    - The image was already being built and pushed with a git-SHA tag (`IMAGE_TAG:
      ${{ github.sha }}` was already defined) — the actual gap was downstream: the Task
      Definition always referenced `:latest`, and `force-new-deployment` just told ECS to
      re-pull whatever `:latest` currently pointed to. No revision was ever tied to a specific
      commit, so there was no clean way to know what was running or roll back to a known-good
      build.
    - Stopped building/pushing the `:latest` tag entirely — only the git-SHA tag exists in ECR
      now. Deliberate scope choice, flagged and confirmed before shipping.
    - Rewrote the `deploy` job to, on every push: build+push the SHA-tagged image, download the
      current live task definition (`aws ecs describe-task-definition`), render a new one with
      the image swapped to that SHA tag (`aws-actions/amazon-ecs-render-task-definition`), then
      register it as a new revision and update the service to it, waiting for rollout stability
      (`aws-actions/amazon-ecs-deploy-task-definition`) — used AWS's own maintained actions
      rather than hand-rolled JSON edits, same class of fragile-JSON-surgery problem hit earlier
      with the Secrets Manager task definition change.
    - This was the CI pipeline's first ever call to `ecs:RegisterTaskDefinition` (needs
      `iam:PassRole` on `ecsTaskExecutionRole` for the CI credentials) — worked on the first try,
      so that permission was already in place.
    - *Verified live*: `gh run watch` showed a clean run (`build-and-test` + `deploy` both
      green, deploy job took 5m34s waiting for stability). Confirmed via
      `aws ecs describe-services`: service running `gha-test-repo-task:4`. Confirmed via
      `aws ecs describe-task-definition`: container image is
      `...gha-test-repo-app:a4d515a012dd39a7bb4ed4c2ab5533f38c5b4d73` — the exact commit SHA
      that triggered the deploy, not `:latest`.

**Current state: fully automated deploy loop from `git push` to live traffic, working, with basic auth in front of the app, the DB password no longer stored in plaintext, the app served over HTTPS at `https://nixverse.skyonix.in/`, CI/CD only runs when app-relevant files actually change, and every deploy is a real Task Definition revision pinned to an immutable git-SHA image tag.**

## Environment variables reference

| Var | Consumed by | Purpose |
|---|---|---|
| `DB_HOST`/`DB_NAME`/`DB_USER` | `DB_CONFIG` in `app.py`, every request that touches Postgres | RDS connection info (plaintext env vars) |
| `DB_PASSWORD` | `DB_CONFIG` in `app.py`, same as above | RDS connection password — as of 2026-08-04, sourced via the Task Definition's `secrets` block from AWS Secrets Manager (`gha-test-repo/db-password`), not a plaintext `environment` entry. ECS resolves it at task launch using `ecsTaskExecutionRole`'s scoped `secretsmanager:GetSecretValue` permission. |
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

**Decision (2026-08-03):** finish every item below, as-is, before starting `JD-HANDS-ON-PLAN.md`
(the bigger AWS Landing Zone / Terraform / EKS / multi-product initiative, queued to start after
this list is fully closed) — including "replace manual console clicks with Terraform." That item
is *not* deferred to the new plan; it gets done here, on the current account, as originally
scoped.

Not urgent, but real production-hygiene items to tackle next, roughly in this order:

1. ~~**`DB_PASSWORD` is a plaintext environment variable** in the Task Definition — move it to
   AWS Secrets Manager and reference it as a secret instead.~~ — fixed 2026-08-04, see step 13
   above. `gha-test-repo-task:3` reads it via the Task Definition's `secrets` block from AWS
   Secrets Manager instead of a plaintext `environment` entry.
2. ~~**No HTTPS** — the ALB only has an HTTP :80 listener. Add an ACM certificate + 443
   listener.~~ — fixed 2026-08-04, see step 14 above. Live at
   `https://nixverse.skyonix.in/`, HTTP redirects to HTTPS.
3. ~~**Mutable `:latest` image tag** — every deploy overwrites the same tag, so there's no clean
   way to know exactly what's running or roll back to a specific past build. Move to immutable
   git-SHA tags with a new Task Definition revision registered per deploy.~~ — fixed 2026-08-04,
   see step 16 above. Every deploy now registers a new Task Definition revision pinned to that
   commit's SHA-tagged image (`gha-test-repo-task:4` currently), no `:latest` tag exists anymore.
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
