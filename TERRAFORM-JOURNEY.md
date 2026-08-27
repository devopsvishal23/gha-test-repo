# Terraform Journey — gha-test-repo

A dedicated record of learning and applying Terraform against this project — separate from
`DEVOPS-JOURNEY.md` (the narrative log of the app's AWS deployment) so this can grow into a real
reference without bloating that doc. `DEVOPS-JOURNEY.md` will get one summary entry once roadmap
item 6 (autoscaling, CloudWatch, Terraform/IaC) is fully closed, pointing back here for detail.

Every step below is timestamped (real `date` output, start and completion) per the user's
standing request — so time-taken per task is visible, not estimated.

## Concepts covered so far

- **What Terraform is**: a tool that lets you describe infrastructure in text files (e.g. "I
  want an S3 bucket named X"), and it figures out the exact AWS API calls needed to make that
  true — then tracks what it created in a **state file**, so it knows what it owns and can
  change or destroy later.
- **The core workflow**: `terraform init` (set up the working directory, download providers) →
  `terraform plan` (show what it *would* do, without doing it) → `terraform apply` (actually do
  it) → `terraform destroy` (tear down what it created).
- **Two fundamentally different Terraform workflows, both being learned deliberately in this
  project**:
  1. **Greenfield** (write code, `apply` from nothing) — practiced first on a throwaway resource
     here, and again for real in `JD-HANDS-ON-PLAN.md`'s Phase 1 (new Landing Zone account).
  2. **Import / brownfield** (adopt already-running resources into Terraform's management
     without touching them) — the actual goal for this repo's existing infra, since it already
     runs live in production with real data. Chosen deliberately over scrap-and-rebuild: avoids
     data loss (RDS has real rows), avoids downtime, avoids re-doing the ACM/DNS pain already
     solved once, and is the more common real-world scenario (most companies inherit existing
     infra rather than starting from nothing).
- **What Terraform can/can't manage here** (decided 2026-08-05, before starting):
  - Can: VPC/subnets (pending check: custom vs. AWS default), security groups, RDS, ALB +
    listeners + target group, ACM certificate, ECS cluster/service/task definition, IAM
    roles/policies, the Secrets Manager secret's *existence/policy* (not recommended to put its
    *value* in Terraform state — state has historically stored attributes in plaintext).
  - Can't: the `skyonix.in` DNS records at the external registrar (no provider configured for
    that registrar), the GitHub Actions workflow YAML and app code (outside Terraform's scope
    entirely — infrastructure only).
  - New consideration once adopted: **drift** — after resources are under Terraform, changes
    should go through Terraform, not console clicks, or code and reality quietly disagree.

## Steps

### Step 1 — Install Terraform, learn the core workflow on a throwaway resource

**Started: 2026-08-05 23:50:54 IST | Completed: 2026-08-06 00:41:18 IST (~51 min)**

- Installed via Homebrew: `brew install terraform`.
- Verified: `terraform version` → `Terraform v1.14.3` on `darwin_arm64` (a newer `1.15.8` exists;
  not urgent to upgrade for learning purposes).
- Practice location: `~/Documents/Devops-Learning-2026/Cloud-SA/terraform-practice-cc/` —
  deliberately **outside** `gha-test-repo` (not a git repo at all), since this is throwaway
  practice, not part of the app's real infrastructure. The *real* import work (next step) will
  live inside `gha-test-repo` itself, in a `terraform/` directory — that distinction was called
  out explicitly so it's never ambiguous which "kind" of Terraform work a given folder is.
- Wrote a minimal `main.tf`: `required_providers` block (declares the AWS provider plugin is
  needed), `provider "aws" { region = "us-east-2" }` (reuses the same credentials the `aws` CLI
  already had configured — nothing extra to set up), and one `resource "aws_s3_bucket"
  "learning_bucket"` with a bucket name suffixed with the AWS account ID (`793110104712`) since
  S3 bucket names must be globally unique across *all* AWS accounts, not just this one.
- Ran the full loop:
  - `terraform init` — downloaded the AWS provider plugin.
  - `terraform plan` — clean preview, `Plan: 1 to add, 0 to change, 0 to destroy`. Covered
    reading plan output: `+`/`~`/`-` symbols for create/change/destroy, `(known after apply)`
    placeholders for values AWS hasn't generated yet.
  - `terraform apply`, typed `yes` — bucket created in 6s. Verified via `aws s3 ls | grep` that
    it was really there, not just Terraform's word for it.
  - **Concept: the state file.** `terraform.tfstate` appeared in the working directory after
    `apply` — this is Terraform's memory of what it owns (exact ARNs/IDs), which is how `plan`
    can compare *this file* vs. *real AWS* vs. *your `.tf` code* to know what changed. Lose the
    file and Terraform has amnesia even if the real resources still exist. This is why real teams
    almost never keep state as a plain local file (fine for this 5-minute exercise) — they store
    it remotely (S3 + a lock table) so it survives and two people don't corrupt it running
    Terraform simultaneously. Same pattern planned for `JD-HANDS-ON-PLAN.md`'s Terraform work.
  - `terraform destroy`, typed `yes` — bucket destroyed in 2s. Verified via `aws s3 ls | grep`
    again: empty result, confirmed gone.
- **Full `init → plan → apply → destroy` loop verified end to end, on a resource with zero
  production impact.**

### Step 2 — Real Terraform project setup (S3 remote state), first real import in progress

**Started: 2026-08-06 00:42:20 IST | Paused (session ended): 2026-08-06 01:23:55 IST**

- Real project lives in `gha-test-repo/terraform/` (not the throwaway practice folder — see Step
  1 for that distinction).
- Remote state set up deliberately with **DynamoDB-based locking** (not the newer native S3
  locking added in Terraform 1.10+ via `use_lockfile` — user wants to learn both approaches
  eventually, DynamoDB first, by explicit choice): S3 bucket `gha-test-repo-terraform-state`
  (versioning enabled) + DynamoDB table `gha-test-repo-terraform-locks`. `backend.tf` written,
  `terraform init` succeeded, provider `hashicorp/aws v5.100.0` installed.
  `.terraform.lock.hcl` committed-worthy (told to keep in git); `.gitignore` added for
  `.terraform/`, `*.tfstate`, `*.tfvars`, etc.
- **Deliberate pacing choice for this whole Terraform arc**: unlike the GitHub Actions work
  (where I wrote most of the YAML directly), I'm handing over `.tf` file *content* for the user
  to create themselves, not editing their `terraform/` files directly — rebuilding hands-on
  muscle memory with this new tool from the start. See [[feedback_devops_learning_style]].
- **First real import target chosen**: `gha-test-repo-db-sg` (`sg-0293d100beac9f3f0`, in
  `vpc-0f3bf3667d5fedbd0`) — simplest existing SG, one ingress rule (TCP 5432 from
  `gha-test-repo-app-sg` / `sg-062d1672a4231f4f3`), default allow-all egress, no tags, no rule
  descriptions set.
- **Resumed 2026-08-06 07:55:33 IST, completed 2026-08-06 08:55:39 IST.**
- *Gotcha #1 — typo'd backend resources*: the S3 bucket and DynamoDB table created for remote
  state were actually named `gha-test-repo-terrform-state` / `-terrform-locks` (missing the "a"
  in "terraform") — `backend.tf` referenced the correctly-spelled names, so the first `terraform
  import` failed with `ResourceNotFoundException` on the DynamoDB table. User temporarily pointed
  `backend.tf` at the typo'd names to keep moving, which required `terraform init -migrate-state`
  (re-initializing after a backend config change — Terraform refuses to silently switch where
  state lives). *Concept*: `-migrate-state` copies existing state from the old backend location
  to the new one; `-reconfigure` just starts fresh at the new location, ignoring the old one —
  `-migrate-state` is the safer default when state might have real content.
  **Fixed properly once state was still trivial**: created correctly-named
  `gha-test-repo-terraform-state` (versioned) + `gha-test-repo-terraform-locks`, fixed
  `backend.tf` (also caught a second typo there — `tfstte` → `tfstate` in the `key`, and
  tightened `encrypt = "true"` (string) to `encrypt = true` (real bool)), ran `terraform init
  -migrate-state` again to move state to the correct backend, verified via `terraform state
  list` that `aws_security_group.db_sg` survived the migration. Executed directly (not handed to
  the user) per their explicit request, since the backend-fix mechanics were already well
  understood and repetitive for them at this point.
- *Gotcha #2 — two real typos in the resource block itself*, caught by `terraform plan` showing
  `must be replaced` instead of a clean import:
  1. `description` was typed as `"Create by RDS Managment Console"` instead of the real
     `"Created by RDS management console"`.
  2. `egress` block's `protocol` was typed as `"tcp"` instead of the real `"-1"` (all protocols).
  - **Concept: `description` on `aws_security_group` is immutable (ForceNew)** — AWS's API
    doesn't support updating it in place, so *any* mismatch (including pure case differences —
    Terraform does exact, case-sensitive string comparison against real AWS state, no fuzzy
    matching anywhere) forces a full destroy-and-recreate of the entire security group, not a
    simple in-place update. Applying that blindly would have briefly deleted
    `gha-test-repo-db-sg` and recreated it with a new ID, breaking the RDS instance's SG
    attachment until reconciled. Caught by scrutinizing the `must be replaced` plan instead of
    applying it — the general rule for import work: never apply a diff, always edit the `.tf` to
    match reality instead.
- **Final verification**: after fixing both typos, `terraform plan` returned `No changes. Your
  infrastructure matches the configuration.` — first real resource fully imported and confirmed
  drift-free.

### Step 3 — Import the rest of the existing infra (VPC/subnets, remaining SGs, RDS, ALB, ACM, IAM, ECS)

**Started: 2026-08-06 09:21:39 IST | Paused (session ended): 2026-08-06 11:18:41 IST**

**Planned order**: VPC + subnets → remaining security groups (`alb-sg`, `app-sg`) → RDS → ALB +
target group + listeners → ACM certificate → IAM role/policy (`ecsTaskExecutionRole`) → ECS
cluster/task definition/service.

**Where we paused**: about to check whether `vpc-0f3bf3667d5fedbd0` (known from the already-
imported `db_sg`) is a custom VPC or AWS's default one — this determines the approach (custom
VPCs get imported and fully managed; a default VPC is more commonly referenced via a Terraform
*data source* rather than imported/owned, since `terraform destroy` on a default VPC is a very
different risk profile). Command handed over but **not yet run**:
```bash
aws ec2 describe-vpcs --vpc-ids vpc-0f3bf3667d5fedbd0 --region us-east-2
```
Next session: run that, check `IsDefault`, then proceed with VPC/subnets accordingly before
moving to the rest of the planned order above.
