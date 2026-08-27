# Interview Q&A — Real Issues from gha-test-repo

Not a generic interview-question dump. Every entry here is a **real problem we actually hit**
while building this project, written up as an interviewer might ask it, with the actual
reasoning behind the fix. Kept separate from `DEVOPS-JOURNEY.md` (the narrative log) and
`TERRAFORM-JOURNEY.md` (the Terraform-specific log) so this can be reviewed on its own before an
interview, without wading through step-by-step build history.

---

### Q: Why does ECS have both an "execution role" and a "task role" — aren't they the same thing?

**What happened**: this repo's task definition has both `executionRoleArn` and `taskRoleArn`
pointing at the same role, which raised the question of why they're separate at all.

**Answer**: they answer different questions. The **execution role** is used by the ECS *agent*
(infrastructure layer) to start the container — pulling the image from ECR, writing logs to
CloudWatch, resolving any `secrets`/SSM parameters referenced in the task definition. The **task
role** is what the *application code* uses at runtime if it calls AWS APIs directly (e.g. a
`boto3` call to S3). Keeping them separate limits blast radius: if the app code were ever
compromised, it would only have the task role's narrow, app-specific permissions — not also
whatever broader infrastructure access the execution role holds. Merging them (as this repo does
today) is harmless only because the app doesn't call any AWS SDKs directly; it becomes a real
risk the moment it does.

---

### Q: An ALB behind a security group is rejecting all traffic on port 80 even though the target group is healthy. What's a likely cause?

**What happened**: the ECS console wizard, when creating the service, attached a single security
group to *both* the ALB and the ECS tasks — that SG only had port 5000 (the app port) open, not
port 80. The ALB itself rejected all inbound HTTP traffic.

**Answer**: a load balancer and its targets should almost always sit behind **separate** security
groups: one on the ALB allowing public traffic on the listener port(s) (e.g. 80/443 from
`0.0.0.0/0`), and one on the compute (ECS tasks/EC2) allowing traffic **only from the ALB's
security group** on the app's actual port. When a single SG is reused for both roles, you either
have to over-open it (defeating the purpose) or it ends up correctly scoped for one side and
wrong for the other — which is exactly what happened here. Fix: split into a dedicated ALB SG and
app SG, with the app SG's ingress rule referencing the ALB SG as its source rather than a CIDR.

---

### Q: You need an HTTPS certificate for an Application Load Balancer — which AWS region do you request it in?

**What happened**: got this wrong by analogy with CloudFront's well-known "always us-east-1"
rule.

**Answer**: ACM certificates for an **ALB must be requested in the same region as the ALB**
(e.g. `us-east-2` if that's where the load balancer lives) — regional resources need regional
certs. **CloudFront is the one well-known exception**, requiring its certificate in `us-east-1`
specifically, regardless of where the distribution's origin lives, because CloudFront is a global
service backed by a single edge cert store. Easy to conflate the two rules since both feel like
"the ACM region for a load-balancing-ish thing," but they're opposite in nature (regional vs.
fixed-global).

---

### Q: A domain's DNS validation record looks completely correct in Route 53, but ACM has been stuck on `PENDING_VALIDATION` for 8+ hours. What's going on?

**What happened**: exactly this. The CNAME record existed, matched ACM's expected name/value
character-for-character, and still never validated.

**Answer**: **owning a domain and having a Route 53 hosted zone for it are two separate things.**
A hosted zone only matters if the domain's actual registrar has its **NS records** (delegation)
pointed at that zone's name servers. If the domain is registered/DNS-hosted elsewhere and nobody
ever repointed the NS records, the Route 53 zone can hold a perfectly correct record that the
public internet — and therefore ACM — never sees, because DNS resolvers never ask that zone
anything. Diagnosed by comparing `dig NS <domain>` (what the internet actually sees) against the
hosted zone's own `DelegationSet.NameServers` (what Route 53 thinks it should be) — a mismatch
confirms it. Fix: either update the NS delegation at the real registrar, or (faster, what we did)
add the validation record directly at the registrar that's actually authoritative.

---

### Q: You added a DNS record with the exact name ACM asked for, at the correct registrar this time — still doesn't validate. Why?

**What happened**: the CNAME name ACM wants for a subdomain (`nixverse.skyonix.in`) looks like
`_hash.nixverse.skyonix.in.` — a multi-label name, not a single label.

**Answer**: most registrar DNS panels expect the record's **Name/Host field entered relative to
the zone**, auto-appending the base domain. Pasting ACM's *full* FQDN into that field silently
creates a doubled suffix: `_hash.nixverse.skyonix.in.skyonix.in.` — which ACM never finds, because
it isn't looking for that. The correct value in a "relative to zone" field is everything **before**
`.skyonix.in` — i.e. `_hash.nixverse`. Some providers (Route 53, Cloudflare) instead want the
full FQDN and handle it correctly as-is — the convention isn't universal, so it's worth checking
which your provider expects. Diagnosed by `dig`-ing both the correct name and the
doubled-suffix version to see which one actually resolved.

---

### Q: DNS is now correct, but the ACM certificate is still sitting in `PENDING_VALIDATION` from before the fix. How do you force it to recheck?

**Answer**: **you can't** — ACM has no manual "recheck now" action for DNS validation, it only
polls on its own schedule. The practical workaround: **delete the stuck certificate request and
issue a fresh one** for the same domain. New requests get an immediate-ish validation attempt,
and since the DNS is now actually correct, it typically validates within minutes. One catch: ACM
generates a brand-new random validation token per request, so you also need to add one more CNAME
record at the registrar (not reuse the old one) — but since the delegation itself is now healthy,
that record propagates fast (its TTL window), not hours.

---

### Q: Your CI/CD pipeline always tags and deploys the same `:latest` image. What's wrong with that, and what's the fix?

**Answer**: a mutable tag means the Task Definition's image reference never actually changes —
every deploy is just "re-pull whatever `:latest` currently points to." There's no way to know,
after the fact, exactly which commit is running, and no way to cleanly roll back to "the build
from two deploys ago" — only to whatever `:latest` happens to be *right now*. Fix: tag every build
with an immutable identifier (commit SHA), and make every deploy register a **new Task Definition
revision** pinned to that exact image tag, then point the service at that specific revision. This
makes "what's running" auditable (`describe-task-definition` shows the exact commit) and rollback
mean something concrete (point the service back at a known-good revision number). Practical
implementation used AWS's own maintained GitHub Actions
(`amazon-ecs-render-task-definition` + `amazon-ecs-deploy-task-definition`) rather than hand-rolled
`jq`/`sed` JSON surgery on the task definition — less fragile, and it's exactly the kind of thing
that's easy to get subtly wrong by hand (see the manual JSON-editing pain in the Secrets Manager
work below).

---

### Q: You added `iam:PassRole`-requiring calls (`RegisterTaskDefinition`) to a CI pipeline for the first time — what could go wrong, and how would you know?

**Answer**: `ecs:RegisterTaskDefinition` requires the calling identity to have `iam:PassRole` on
whatever execution/task roles the new revision references — without it, the call fails with an
`AccessDenied` on PassRole. The safe way to find out is to just try it: registering a task
definition is non-destructive if it fails (nothing about the running service changes), so there's
no real risk in attempting it and reading the actual error rather than pre-auditing every IAM
policy defensively beforehand.

---

### Q: A GitHub Actions workflow has no `paths` filter, so *any* commit — including a docs-only change — triggers a full rebuild and redeploy. How do you fix it, and what's the trade-off between the two ways of doing it?

**Answer**: add a `paths` (allowlist — only these paths trigger the workflow) or `paths-ignore`
(blocklist — everything except these paths triggers it) filter to the `push`/`pull_request`
trigger. **Allowlist is generally safer**: any new non-code file added later (more docs, config)
won't accidentally trigger a build unless someone remembers to exclude it — a blocklist only
stays correct if someone remembers to keep adding to it. One real gotcha to know before relying on
this: if branch protection ever requires this workflow's checks to pass before merging, a
path-filtered workflow that *doesn't run* (because a PR only touched docs) can leave that required
check stuck "pending" forever, blocking the merge — GitHub doesn't auto-satisfy a required check
that never ran.

---

### Q: An admin-seeding function only creates the admin user if it doesn't exist. Why doesn't changing the password env var and redeploying rotate it?

**Answer**: "insert if missing" and "rotate on change" are different pieces of logic — the
original code only ever checked "does this username exist?" and did nothing if it did, so an
existing admin's stored password hash was never touched again after creation. Fix: also compare
the current env var against the stored hash (`check_password_hash`) — if the user exists but the
password no longer matches, update the hash; if it already matches, do nothing (avoids a pointless
write on every restart). This makes the env var the authoritative source of truth on every boot,
without needing a hidden control DB update to rotate credentials.

---

### Q: In an AWS Landing Zone / Control Tower setup, why should the "management account" stay empty of actual workloads?

**Answer**: the management account is the root of trust for the whole organization — it can
create/close member accounts, apply org-wide guardrails (SCPs), and see billing across everything.
Running production workloads there means a compromise or mistake in "just another app" carries the
blast radius of the entire organization's control plane, not just that one app. Best practice:
promote the account to management-only, and vend a fresh **member account** via Account Factory
for actual infrastructure — keeping the account that can affect everything separate from the
accounts that run things.

---

### Q: Can you just delete an AWS account you don't need anymore in an Organization?

**Answer**: not instantly. Removing/closing a member account goes through AWS's suspension
process — it lands in a **Suspended OU** state for roughly 90 days before actual closure, not an
immediate delete. Account *creation* is cheap and fast; account *closure* is a real, multi-week
commitment. Worth knowing before spinning up throwaway accounts casually in a real org.

---

### Q: Why does Terraform need a "state file" at all — why not just read the real infrastructure directly every time?

**Answer**: the state file is Terraform's record of exactly what it created (real ARNs/IDs, full
attribute values) — it's what lets `plan` compare *state* vs. *real infrastructure* vs. *your
`.tf` code* to figure out what (if anything) needs to change, without re-deriving everything from
scratch via slow, incomplete API calls every time. Lose the file and Terraform has amnesia about
what it owns, even if the real resources still exist. This is why teams essentially never keep
state as a plain local file in anything beyond a five-minute solo exercise — they store it
remotely (S3 + a locking mechanism) so it survives, and so two people running Terraform at once
don't corrupt each other's changes.

---

### Q: What's the difference between `terraform init -migrate-state` and `terraform init -reconfigure`, and why does picking the wrong one matter so much?

**What happened**: hit this directly after a backend config change (fixing a typo'd S3
bucket/DynamoDB table name) triggered "Backend configuration changed" on `terraform init`.

**Answer**: `-migrate-state` copies existing state from the *old* backend location to the *new*
one before switching — the safe default whenever state might already contain real content.
`-reconfigure` just starts using the new backend location fresh, **ignoring** whatever was at the
old one. Picking `-reconfigure` when real state exists at the old location means Terraform now
has zero record of everything it previously created — a subsequent `apply` would see "nothing
exists yet" and could try to recreate resources that are already running, or (worse, at larger
scale) a bad flag choice combined with a live production state file is exactly the kind of mistake
that can lead to Terraform trying to destroy/recreate real infrastructure it's lost track of. Low
stakes in this project (a single security group), extremely high stakes at company scale.

---

### Q: `terraform plan` shows a security group `must be replaced` instead of just updating, over what looks like a small text difference. Why does that force a full destroy-and-recreate?

**What happened**: a typo in the security group's `description` field (`"Create by RDS Managment
Console"` vs. the real `"Created by RDS management console"`).

**Answer**: `description` on `aws_security_group` is an **immutable (ForceNew) attribute** in
AWS's API — it cannot be updated on an existing security group, only set at creation time. Any
mismatch between your `.tf` code and the real value — including a pure **case** difference, since
Terraform does exact, case-sensitive string comparison with no fuzzy matching anywhere — forces
Terraform to plan a full destroy-then-create of the entire resource, not a simple field update.
Blindly applying that plan would have deleted the real, in-use security group and recreated it
with a new ID, breaking whatever referenced the old one (here, the RDS instance's SG attachment)
until manually reconciled. The general discipline this reinforces for **import work specifically**:
never apply a diff you didn't expect — always edit the `.tf` code to match reality, and only ever
`apply` once `plan` shows zero changes.

---

---

### Q: ECS tasks show as `RUNNING` with no stopped reason, but the ALB's target group marks them `unhealthy` with `Target.Timeout`. Where do you look?

**What happened**: during the 2026-08-27 rebrush rebuild, tasks launched fine and stayed running,
but the target group health checks kept timing out. `aws ecs describe-tasks` showed nothing wrong
(no `stoppedReason`, no container exit code) — the problem wasn't the task, it was the network
path *to* the task.

**Answer**: when a "running, healthy-looking task" still fails ALB health checks, the task itself
is rarely the cause — check the security-group path between the ALB and the target next.
`aws elbv2 describe-load-balancers --query 'LoadBalancers[0].SecurityGroups'` showed the ALB was
attached to `app-sg` (`sg-0ca57...`) instead of the dedicated `alb-sg`. Since `app-sg`'s only
inbound rule allows port 5000 from `alb-sg`'s ID specifically, and the ALB's own traffic was now
sourced from `app-sg` (not `alb-sg`), that rule didn't match — health-check requests were silently
dropped, producing a timeout with zero signal on the ECS side. Notably, this is the **exact same
root cause** as the SG entry above (a single SG reused for both ALB and tasks) — it recurred here
even after explicitly selecting the correct SGs in the service-creation wizard, because the
**load balancer's** SG field defaulted back to the app SG independently of the **service's**
network config field right next to it. Lesson: two separate dropdowns in the same wizard can each
silently default wrong in different directions — after using any "create service + ALB together"
wizard, always verify both attachments independently with the CLI
(`describe-load-balancers` for the ALB's SG, `describe-services` for the task's SG) rather than
trusting that picking the right option once in the UI stuck everywhere it needed to.

---

### Q: `docker push`ing an image built locally works fine, but ECS Fargate fails every task with `CannotPullContainerError: ... does not contain descriptor matching platform 'linux/amd64'`. What's wrong?

**What happened**: rebuilding the app's bootstrap image on an Apple Silicon Mac with a plain
`docker build`, then pushing it to ECR, produced an image manifest with no `linux/amd64` variant
at all — Fargate's task definition (CPU architecture `X86_64` by default) had nothing it could
pull.

**Answer**: `docker build` targets the **host machine's architecture** by default, not a fixed
platform — on Apple Silicon that's `arm64`. AWS Fargate tasks default to `X86_64` (`amd64`) unless
the task definition explicitly opts into `ARM64` (Graviton). Building without `--platform` on an
ARM host and deploying to a default-architecture Fargate task is therefore a silent mismatch: the
push succeeds, ECR stores the image fine, and the failure only surfaces later at task-launch time
with a manifest error that doesn't obviously point at "architecture." Fix: build with
`docker buildx build --platform linux/amd64 ... --push` explicitly whenever building locally on
Apple Silicon for a `X86_64` Fargate target. This is specific to **local** builds — CI runners
(e.g. GitHub Actions' `ubuntu-latest`) are `amd64` by default, so images built there never hit
this.

---

*Living document — add new entries here as real issues come up, in the same style: the actual
question shape, the real scenario, and the full reasoning, not just the fix.*
