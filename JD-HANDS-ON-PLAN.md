# JD Hands-On Practice Plan — gha-test-repo as the Base App

**v3** — updated after discussion on 2026-08-03. See "What changed from v2" below.

**STATUS: QUEUED.** By your call, this plan starts only after every item in `DEVOPS-JOURNEY.md`'s
"Known gaps / roadmap ahead" is closed out on the current live app. Don't start Day 1 of this
plan until that doc says the old roadmap is done.

A now ~18-working-day plan to turn the JD you shared into real, executed, hands-on work — using
two real products as the training ground instead of toy tutorials:
- **Nixace-Student-Portal** (the Flask + Postgres app currently named `gha-test-repo`, already
  live on ECS Fargate — see `DEVOPS-JOURNEY.md`). Rename is planned, not yet done to the actual
  repo/code — happens when Phase 1 of this plan starts, not before.
- **habit-tracker** (your second product) — used from Phase 0 onward as the second real
  consumer of every reusable Terraform module and Helm chart, proving reusability instead of
  just asserting it.

**How to use this doc:** it's the map, not the turn-by-turn instructions. When we sit down to
actually *do* a day, we'll work it exactly like `DEVOPS-JOURNEY.md` so far — one step at a time,
I explain the why, give you the exact command or console clicks, you run it and report back,
then we move on. This doc just tells us where we are on the map and why that day exists.

## What changed from v2 (your calls, 2026-08-03)

1. **Sequencing: finish the original roadmap first, as-is, in full.** This plan is now explicitly
   queued, not running alongside `DEVOPS-JOURNEY.md`. That includes "replace manual console clicks
   with Terraform" — that item is done on the *current* account, as originally scoped, not
   deferred here. Phase 1 below still does its own Terraform work afterward, in the new
   Landing-Zone account — yes, that means Terraform gets written twice (once for the current flat
   account, once for the new one), which I'd flagged as avoidable duplication, but the user's call
   stands: close the old roadmap exactly as scoped first.
2. **Cost philosophy changed.** You're treating this as an investment, not an expense to
   minimize — so cost is no longer a reason to trim scope. I'll still report real numbers as they
   come up (so you always know what's running), but won't use cost to argue for a smaller plan.
3. **Phase 0 (Landing Zone) expanded from 3 days to 5** to cover the full enterprise OU/account
   structure you shared (Security OU, Infra OU with Network + Shared Services accounts,
   Prod-Workload vs Non-Prod/UAT-Workload OUs, Sandbox OU, Suspended OU) instead of the earlier
   minimal version.
4. **Two real products, not one app + fake tenants.** habit-tracker joins as a second real
   consumer of every module — this is a stronger proof of "reusable Terraform modules" than a
   synthetic second copy of the same app, and it maps naturally onto the Prod-Workload OU having
   multiple business-unit-style accounts.
5. One deliberate judgment call, not a cost-driven cut: the diagram's **Network Account**
   normally centralizes connectivity via **Transit Gateway** (hub-and-spoke). We'll build the
   account for real and understand what belongs there, but not stand up paid Transit Gateway
   attachments by default — that's a specific, addable experience later if you want it
   specifically, not a scope-reduction.
6. Net effect: plan grew from 16 to ~18 days. Flagging the growth explicitly rather than quietly
   absorbing it.

---

## Ground rules

1. **Don't start this plan until `DEVOPS-JOURNEY.md`'s roadmap is fully closed.** See STATUS
   above.
2. **Don't touch the live production path until we've built its replacement.** The current
   ECS/RDS/ALB setup keeps running throughout Phase 0-1; we only "cut over" once the
   Terraform-managed version in the new account is proven live.
3. **Report real costs transparently, but don't let them gate scope.** Landing Zone: modest
   ongoing Config/CloudTrail/S3 cost that scales with actual resource count and activity (not a
   flat tax on account existence — an empty vended account costs close to nothing). EKS,
   Aurora, and (if ever added) Transit Gateway are the real recurring-cost items — always called
   out per day, treated as informed choices, not blockers.
4. **Pace is flexible.** ~1-2 hrs/day assumed. Heavier days (Control Tower launch, EKS+Helm) can
   split across two sessions.
5. **Every day ends with a checkpoint** — something you can point to and say "this now exists and
   I proved it works."

---

## Important operational realities (read before Day 1)

- **Account creation is instant; account closure is not.** Once a member account joins your
  Organization, removing it later goes through AWS's ~90-day suspension process (it lands in the
  **Suspended OU** — see Day 5), not an immediate delete.
- **The management account should stay empty (no workloads).** Day 1 promotes your current AWS
  account to be the Organization's management account. All real infrastructure — both products,
  both environment tiers — lives in vended member accounts from Day 3 onward.
- **Landing Zone accounts organize by product/environment, not by end-customer.** Real Landing
  Zones vend accounts per business unit or environment tier (exactly what Nixace-Student-Portal
  vs. habit-tracker, and Prod vs. Non-Prod, map onto). End-customer multi-tenancy (if either
  product ever needs it) is a namespace-level concern inside one account, not an account-per-
  customer pattern — kept as a stretch item, see Day 13.
- **IAM Identity Center (AWS SSO)** becomes your login path into every member account once
  Control Tower is live.

---

## The 18-day map

| Day | Phase | JD skill area | What we build |
|---|---|---|---|
| 1 | 0 — Landing Zone | AWS Organizations + Control Tower | Launch landing zone: management account, auto-created Log Archive + Audit accounts (Security OU) |
| 2 | 0 | Full OU tree + Infra accounts | Build Infra OU (Network Account, Shared Services Account), Prod-Workload OU, Non-Prod/UAT-Workload OU, Sandbox OU |
| 3 | 0 | Account Factory | Vend 4 workload accounts: `nixace-student-portal-{prod,nonprod}`, `habit-tracker-{prod,nonprod}` |
| 4 | 0 | Guardrails (SCPs) per OU tier | Stricter SCP on Prod-Workload OU, looser on Non-Prod/Sandbox; IAM Identity Center permission sets per OU |
| 5 | 0 | Sandbox + Suspended OU | Sandbox account for free experimentation; deregister a disposable test account and watch it land in Suspended OU |
| 6 | 1 — Terraform + ECS | Terraform + S3 | Remote state (S3 + DynamoDB lock), reused across both products |
| 7 | 1 | Terraform + VPC | Reusable VPC module, first run: `nixace-student-portal-prod` |
| 8 | 1 | Terraform + ALB (+ HTTPS) | ALB + security-group module, ACM cert + 443 listener folded in (closes old roadmap's HTTPS item, properly, via IaC) |
| 9 | 1 | Aurora PostgreSQL + Secrets Manager | Aurora module + Secrets Manager for DB creds |
| 10 | 1 | Terraform + ECS | ECS cluster/service/task-def module — Nixace-Student-Portal live end-to-end in its new account |
| 11 | 2 — EKS + Helm | Terraform + EKS | EKS cluster + managed node group module |
| 12 | 2 | Helm | Nixace-Student-Portal as a Helm chart on EKS, readiness/liveness probes validated |
| 13 | 2 | Second product + (optional) namespaces | Re-run Day 7-12 modules against `habit-tracker-prod` — the real reusability proof; optional stretch: tenant-a/b namespaces inside one product if you want the multi-customer pattern too |
| 14 | 3 — Config + CI/CD | Centralized YAML config | One YAML source (per product/env) → generates `.tfvars` + Helm `values.yaml` |
| 15 | 3 | Jenkins CI + JFrog Artifactory (Shared Services account) | Lint/test/build/version(git-SHA) pipeline — hosted in the Shared Services account, publishing to Artifactory |
| 16 | 3 | Jenkins CD, sequenced, per product | infra (terraform) → DB migration → Helm deploy, parameterized by product/env |
| 17 | 3 | Python/Bash + rollback | Validation scripts (API/DB/ALB) + simulated-failure rollback drills |
| 18 | 4 — Wrap-up | Harness (light) + retro | Quick Harness pipeline taste, JD-coverage retro, full teardown checklist |

**Optional, not on the critical path:** a tiny Java/Maven microservice purely to produce a real
Maven BOM and push it through the Day 15 Artifactory setup — slot in anytime after Day 15.

---

## Day-by-day detail

### Day 1 — Launch the Landing Zone (AWS Organizations + Control Tower)
**Why:** foundational governance layer the JD names first — everything else lives inside the
account structure created here.
**Build:** enable AWS Organizations, launch Control Tower (your current account becomes the
**management account**), Control Tower auto-creates **Log Archive** and **Audit** accounts under
a `Security` OU.
**Checkpoint:** Control Tower dashboard shows landing zone status "Active"; three accounts exist
(management + Log Archive + Audit); you can explain what each is for.

### Day 2 — Build the full OU tree + Infra accounts
**Why:** this is the piece that makes it a real enterprise-shaped Landing Zone rather than a
minimal one — matches the diagram you shared.
**Build:** create OUs: `Infra` (containing a **Network Account** and a **Shared Services
Account**), `Prod-Workload`, `Non-Prod-Workload` (a.k.a. UAT), `Sandbox`. Vend the Network and
Shared Services accounts via Account Factory.
**Checkpoint:** full OU tree visible in Organizations, matching (in spirit) the reference
diagram; Network and Shared Services accounts exist and you can log into both.

### Day 3 — Account Factory: vend the workload accounts
**Why:** gives both real products a proper home, split by environment tier from day one.
**Build:** vend `nixace-student-portal-prod`, `nixace-student-portal-nonprod` into
`Prod-Workload`/`Non-Prod-Workload` respectively; same for `habit-tracker-prod` /
`habit-tracker-nonprod`.
**Checkpoint:** four accounts exist, correctly placed in their OUs.

### Day 4 — Guardrails (SCPs) per OU tier + IAM Identity Center
**Why:** JD wants "enterprise cloud standards" — guardrails are how Landing Zones enforce
different rules for different risk levels (Prod vs. Sandbox), and SSO is how you'll actually work
across five-plus accounts going forward.
**Build:** a stricter SCP on `Prod-Workload` (e.g., deny deleting resources tagged `env=prod`,
restrict region), a looser one (or none) on `Sandbox`; IAM Identity Center permission sets scoped
per OU (e.g., admin in Sandbox, restricted in Prod-Workload).
**Checkpoint:** attempt the denied action in Prod-Workload and watch it get blocked; confirm the
same action succeeds in Sandbox — proves the guardrails are tier-aware, not a single blanket
rule.

### Day 5 — Sandbox + Suspended OU
**Why:** Sandbox gives you a genuinely consequence-free account to experiment in; Suspended OU is
where deregistered accounts land — directly answers the "what happens when I delete an account"
question from earlier.
**Build:** vend a Sandbox account with minimal guardrails; create and then deregister a disposable
throwaway account.
**Checkpoint:** watch the deregistered account move into the Suspended OU and observe its state —
concrete proof of the ~90-day closure process instead of taking it on faith.

### Day 6 — Terraform remote state (S3)
**Why:** first real Terraform work; state bucket is shared infrastructure both products' configs
will reference.
**Build:** S3 bucket for state + DynamoDB lock table, `backend.tf` (likely living in the Shared
Services account, referenced by both products' Terraform).
**Checkpoint:** `terraform init`/`plan` succeed against the new backend.

### Day 7 — Terraform VPC module
**Why:** reusable modules, explicitly named in the JD — first real instantiation.
**Build:** `modules/vpc`, applied to `nixace-student-portal-prod`.
**Checkpoint:** VPC created via `terraform apply`, destroyed cleanly via `terraform destroy`.

### Day 8 — Terraform ALB + security-group module (+ HTTPS)
**Why:** codifies the ALB→app→db SG pattern you already hand-built once; folding in the ACM/HTTPS
listener here closes that old-roadmap item properly, via IaC, instead of doing it twice.
**Build:** `modules/alb` (including an ACM cert + 443 listener), `modules/security-groups`.
**Checkpoint:** ALB live via Terraform over HTTPS, SG chain matches the documented pattern.

### Day 9 — Aurora PostgreSQL + Secrets Manager
**Why:** JD names Aurora specifically (not just RDS); Secrets Manager is done here via Terraform
since the secret *is* the Aurora connection info.
**Build:** `modules/aurora-postgres` + a Terraform-managed Secrets Manager secret.
**Checkpoint:** connect to Aurora using credentials pulled live from Secrets Manager — nothing
plaintext anywhere in the config.

### Day 10 — Terraform ECS (cluster, service, task definition)
**Why:** brings Phase 1 to a real, running app in its proper account.
**Build:** `modules/ecs-service`, task definition pulling the Secrets Manager secret, wired to
Days 7-9.
**Checkpoint:** Nixace-Student-Portal reachable via the new ALB's HTTPS DNS name, connected to
Aurora, login/health checks working — the "old app, new proper home" milestone.

### Day 11 — Terraform EKS module
**Why:** biggest net-new skill in the JD.
**Build:** `modules/eks` — control plane + small managed node group, OIDC provider enabled.
**Checkpoint:** `kubectl get nodes` healthy.

### Day 12 — Helm chart + EKS deploy
**Why:** JD wants Helm-based deploys with real readiness/probe validation.
**Build:** Helm chart for Nixace-Student-Portal — Deployment/Service, probes on `/health`,
`values.yaml`.
**Checkpoint:** `helm install` succeeds, pods `Ready`; break the probe path temporarily to prove
it actually gates readiness, then fix it.

**Parked assignment (added 2026-08-28, from a gha-test-repo rebrush session):** once EKS + Helm is
live here, revisit production application logging via ELK/EFK — Fluent Bit as a DaemonSet tailing
`/var/log/containers/*`, shipped to Elasticsearch (or AWS OpenSearch as the managed option),
visualized in Kibana. Conceptual discussion already happened (shipper → Elasticsearch → Kibana
pipeline, ILM for index retention, Logstash as an optional parsing layer, managed vs. self-hosted
tradeoffs); this is the hands-on follow-up, deliberately deferred until there's a real EKS cluster
to wire it into rather than doing it in the abstract.

### Day 13 — Second product proves reusability (+ optional namespace tenancy)
**Why:** this is the real test of "reusable Terraform modules for consistent environment
provisioning" — running the same modules against a genuinely different app, not a copy.
**Build:** re-run the Day 7-12 modules (VPC, ALB, Aurora/Secrets Manager, ECS or EKS+Helm) against
`habit-tracker-prod`, changing only `.tfvars`/Helm values.
**Checkpoint:** habit-tracker live in its own account using the identical module code. *Stretch,
optional:* if you also want the end-customer multi-tenancy pattern specifically, add
tenant-a/tenant-b namespaces inside one product's EKS cluster with isolated Aurora
databases/schemas.

### Day 14 — Centralized YAML config → tfvars + Helm values
**Why:** named directly in the JD.
**Build:** `config/<product>-<env>.yaml` + a Python script rendering it into
`terraform.tfvars.json` and `values-<product>-<env>.yaml` for both products.
**Checkpoint:** one YAML edit propagates into both a `terraform plan` diff and a `helm upgrade
--dry-run` diff, for either product.

### Day 15 — Jenkins CI + JFrog Artifactory (Shared Services account)
**Why:** JD wants Jenkins-based CI and Artifactory publishing; hosting Jenkins in the Shared
Services account (not duplicated per product) is the standard real-world pattern a Landing Zone
enables.
**Build:** Jenkins via Docker in the Shared Services account, `Jenkinsfile` (lint → test → build →
tag with git-SHA — closes the old roadmap's immutable-tag item), push image + version manifest to
a free-tier JFrog Artifactory instance.
**Checkpoint:** pipeline green on a clean push, red on a deliberate lint error, green again once
fixed; artifact visible and pullable from Artifactory, tagged with a real git SHA (no more
`:latest`).

*Optional side-quest slot:* a tiny Java/Maven microservice here purely to produce a real Maven
BOM through this same Artifactory pipeline — doesn't block Day 16+.

### Day 16 — Jenkins CD, sequenced, per product
**Why:** JD wants CD that provisions infra → deploys DB changes → deploys services, in order,
across environments — ties Phases 1-3 together into one pipeline.
**Build:** pipeline stages: `terraform apply` (target product/env's infra) → DB migration →
`helm upgrade`/ECS deploy, parameterized using the Day 14 YAML.
**Checkpoint:** trigger for Nixace-Student-Portal, watch all three stages run in order, confirm
habit-tracker untouched; repeat for habit-tracker.

### Day 17 — Python/Bash validation scripts + rollback drills
**Why:** JD wants automation scripts validating APIs/e2e/DB/ALB routing, and rollback mechanisms
proven against simulated failures.
**Build:** smoke-test script (health/login/core flow), DB-connectivity check, ALB target-group
health check — runnable against either product; deliberately deploy a broken image via Helm and
via a bad ECS task definition revision, compare `helm rollback` (manual) vs. ECS's circuit breaker
(automatic).
**Checkpoint:** scripts catch the broken deploy, both rollback paths self-heal, and you can
articulate which behavior you'd want on-call and why.

### Day 18 — Harness (light touch) + retro + teardown
**Why:** Harness is on the JD but demoted per your call — one small pipeline is enough to not be
purely theoretical.
**Build:** one small Harness free-tier pipeline mirroring the Day 15 CI stage; a retro doc
(`JD-COVERAGE.md`) mapping every JD bullet to what was actually built, across both products.
**Checkpoint:** decide deliberately what to keep running long-term vs. tear down — note Landing
Zone accounts are **not** instantly closeable (see operational realities above).

---

## JD coverage matrix

| JD requirement | Covered on day(s) |
|---|---|
| AWS Landing Zone / Control Tower (full OU/account tree) | 1, 2, 3, 4, 5 |
| Secure/scalable/reusable AWS solutions | 7, 8, 9, 11, 13 (reuse proof) |
| VPC | 7 |
| EKS | 11, 12, 13 |
| Aurora PostgreSQL | 9 |
| ALB (+ HTTPS) | 8 |
| Secrets Manager | 9 |
| S3 | 6 (remote state) |
| Terraform + reusable modules | 6-13, proven twice via two real products |
| Centralized YAML → tfvars/Helm values | 14 |
| Jenkins CI/CD | 15, 16 |
| Harness | 18 (light touch, by your call) |
| Linters, QA checks, artifact packaging, versioned outputs (git-SHA) | 15 |
| Maven BOM | optional side-quest (separate Java service, by your call) |
| JFrog Artifactory | 15 |
| CD: infra → DB → service, sequenced, per product/env | 16 |
| Helm deploy + readiness/probes | 12 |
| API/e2e/connectivity/DB/ALB validation | 17 |
| Rollback validation | 17 |
| Python/Bash automation | 14, 17 |
| Multi-tenant infrastructure | 2-5 (account/OU-level, real) + 13 (namespace-level, optional stretch) |

**Still worth naming honestly:** Harness gets one day's worth of depth, not fluency. Maven BOM is
a deliberate detour into a different language ecosystem. Both are called out here so you know
exactly what depth to claim in an interview.
