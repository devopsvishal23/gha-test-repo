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
  gha-test-repo-app-sg  -> inbound 5000 from 0.0.0.0/0 (should be tightened to ALB-only, see Known Gaps)
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

**Current state: fully automated deploy loop from `git push` to live traffic, working.**

## Known gaps / roadmap ahead

Not urgent, but real production-hygiene items to tackle next, roughly in this order:

1. **`DB_PASSWORD` is a plaintext environment variable** in the Task Definition — move it to
   AWS Secrets Manager and reference it as a secret instead.
2. **No HTTPS** — the ALB only has an HTTP :80 listener. Add an ACM certificate + 443 listener.
3. **Mutable `:latest` image tag** — every deploy overwrites the same tag, so there's no clean way
   to know exactly what's running or roll back to a specific past build. Move to immutable
   git-SHA tags with a new Task Definition revision registered per deploy.
4. **`gha-test-repo-app-sg` allows inbound 5000 from `0.0.0.0/0`** — should be tightened to only
   accept traffic from the ALB's security group, since the ALB is the only thing that should be
   able to reach the app directly.
5. Not yet discussed, natural next topics: autoscaling policies, CloudWatch alarms/monitoring,
   replacing manual console clicks with Terraform (IaC).
6. `Dockerfile.multistage` in the repo root is unused by this pipeline and has a stale
   `EXPOSE 8000` (app actually listens on 5000) — reconcile before ever switching to it.
