# GitHub Actions Concepts — deep dive on `.github/workflows/flask-postgres.yml`

A dedicated walkthrough of this repo's actual CI/CD workflow, section by section, done because
GitHub Actions/CI YAML was flagged as this project's weakest-understood area (most of it was
written directly rather than hand-built, unlike everything else in this project). This is not a
generic GHA tutorial — every example below is the real file in this repo.

Read `.github/workflows/flask-postgres.yml` alongside this doc.

## The big picture: what a workflow file *is*

A GitHub Actions workflow is YAML describing three things: **when to run** (`on:`), **what
variables are available everywhere** (`env:`), and **one or more jobs** (`jobs:`) — each job is a
separate virtual machine GitHub spins up fresh, runs your steps on, then throws away.

```yaml
name: CI/CD           # just a label, shown in the Actions tab UI
on: ...                # WHEN this workflow fires
env: ...                # variables available to every job/step below
jobs:
  build-and-test: ...   # job #1
  deploy: ...            # job #2
```

**Key mental model — job isolation:** `build-and-test` and `deploy` are two *separate* machines.
Nothing in one is visible to the other automatically (no shared filesystem, no shared shell
variables) — that's why `deploy` starts with its own `Checkout code` step even though
`build-and-test` already checked out the same code. Anything a job needs, it has to
fetch/build/receive itself — the only way to pass data between jobs is explicit **job outputs**
(a different, coarser mechanism than the **step outputs** covered further down).

## The trigger block: `on:`

```yaml
on:
  push:
    branches: [main]
    paths: ['app.py', 'requirements.txt', 'dockerfile', 'docker-compose.yml', 'templates/**',
             '.github/workflows/flask-postgres.yml']
  pull_request:
    branches: [main]
    paths: [... same list ...]
```

Runs when either a **push** lands on `main`, or a **pull_request** is opened/updated *targeting*
`main` — but only if the changed files match `paths:`.

**Why `paths:` exists:** without it, any commit to `main` — even a one-line doc typo fix — would
trigger a full build+test+deploy cycle. Wasted CI minutes, and worse, an unnecessary production
deployment for a change that never touched the app. `templates/**` is a glob: `**` means "this
folder and everything inside it, any depth" (`templates/*` would only match files directly
inside, not subfolders). **Confirmed via a check-yourself question:** a commit that only touches
`INTERVIEW-QA.md` does **not** trigger this workflow at all.

**Why both `push` and `pull_request` are listed with the identical path filter** — they serve
different purposes despite looking the same:
- `pull_request` fires *before* a merge — runs `build-and-test` (job 1) as a PR check, so you see
  red/green on the PR before merging bad code into `main`.
- `push` fires *after* a merge/direct push lands on `main` — this is the only trigger allowed to
  also run `deploy` (job 2), enforced separately via job 2's own `if:` condition (see below).

## The `env:` block

```yaml
env:
  AWS_REGION: us-east-2
  ECR_REPOSITORY: gha-test-repo-app
  IMAGE_TAG: ${{ github.sha }}
```

Two are plain strings. `IMAGE_TAG` uses `${{ ... }}` — GitHub Actions' **expression syntax**, how
you pull in dynamic values instead of hardcoding them. `github.sha` is a built-in **context**
(GitHub automatically exposes info about the triggering event under `github.*`) — the full
40-character commit SHA that triggered this run. **This is why images are tagged with git-SHAs
instead of `:latest`** — every image is traceable to the exact commit that built it.

These three vars are visible in every job/step below — referenced as `$AWS_REGION` inside a shell
`run:` step, or `${{ env.AWS_REGION }}` inside another action's `with:` block. Both forms appear
in this file.

## Job 1: `build-and-test`

```yaml
build-and-test:
  runs-on: ubuntu-latest
  steps:
    - name: Checkout code
      uses: actions/checkout@v4
    - name: Build image
      run: docker build -t docker-practice-app:test .
    - name: Start app + db via Compose
      run: docker compose up -d --build
    - name: Wait for /health to pass
      run: |
        for i in $(seq 1 15); do
          if curl -sf http://localhost:5000/health; then
            echo "App is healthy"; exit 0
          fi
          echo "Waiting for app... ($i/15)"; sleep 3
        done
        echo "App failed health check"; docker compose logs; exit 1
    - name: Tear down
      if: always()
      run: docker compose down -v
```

**`uses:` vs `run:` — the core distinction of every step:**
- `uses:` — run someone else's pre-packaged action (reusable automation published to the
  Marketplace or written by GitHub). `actions/checkout@v4` clones your repo onto the runner —
  without it, the runner is an empty Ubuntu VM with no access to your code at all.
- `run:` — execute raw shell commands directly on the runner, same as typing them in your own
  terminal.

**The `|` after `run:`** is YAML's block-scalar syntax — everything indented below is one
multi-line string, letting you write a whole shell script (loops, conditionals) as a single step.

**`if: always()`** on the teardown step: by default, if any earlier step fails, GitHub Actions
skips all remaining steps in that job. `always()` overrides that — this step runs regardless of
pass/fail, so containers don't leak into whatever runs next on that runner.

**Why bother running a real `docker compose up` + health check on a throwaway Ubuntu VM at all,
instead of just building and moving on?** To check the container starts and is genuinely healthy
*before* it ever reaches the production ECS environment — catching a broken image here is cheap;
finding out via a failed ECS deployment is not.

## Job 2, part 1: the gate + AWS auth + image push

```yaml
deploy:
  needs: build-and-test
  if: github.ref == 'refs/heads/main' && github.event_name == 'push'
  runs-on: ubuntu-latest
  steps:
    - name: Checkout code
      uses: actions/checkout@v4
    - name: Configure AWS credentials
      uses: aws-actions/configure-aws-credentials@v4
      with:
        aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
        aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        aws-region: ${{ env.AWS_REGION }}
    - name: Login to Amazon ECR
      id: ecr-login
      uses: aws-actions/amazon-ecr-login@v2
    - name: Build, tag, and push image
      id: build-image
      env:
        ECR_REGISTRY: ${{ steps.ecr-login.outputs.registry }}
      run: |
        docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
        docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
        echo "image=$ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG" >> $GITHUB_OUTPUT
```

**`needs: build-and-test`** is what actually enforces "job 1 must pass before job 2 starts."
Without it, both jobs run in parallel by default, fully independent. This is the mechanism that
makes job 1's health check actually gate the deployment.

**`if: github.ref == 'refs/heads/main' && github.event_name == 'push'`** is the real teeth behind
"only deploy from a direct push to main, never a PR." The `on:` block lets *both* `push` and
`pull_request` trigger the whole workflow — this `if` is what stops `deploy` from ever running
during a PR check, even though `build-and-test` runs for both.

**`secrets.AWS_ACCESS_KEY_ID` / `secrets.AWS_SECRET_ACCESS_KEY`** aren't in this file at all —
they live encrypted in the repo's GitHub settings (Settings → Secrets and variables → Actions) and
are substituted in only at runtime. This is why the workflow authenticates to AWS without
credentials ever appearing in this YAML or in any log output.

**Why `configure-aws-credentials` is its own separate step**, rather than folded into the
build/push step: it sets up the AWS session (credentials the AWS CLI/SDK both read) for **the
rest of the job**, not just one step. Everything after it — `ecr-login`, the
`describe-task-definition` call, and the final deploy action — all need that same AWS access.
Running it once, early, means every later step inherits the authenticated session.

**The `id: ecr-login` / `id: build-image` pattern — step outputs**, the mechanism for passing a
value *between steps within the same job* (finer-grained than the job-isolation/job-outputs
concept above):
- `id: ecr-login` tags that step so it can be referenced later.
- That action produces an output called `registry` (the actual ECR URL for your account) — read
  as `${{ steps.ecr-login.outputs.registry }}`.
- The next step manually creates its *own* output the same way: `echo "image=..." >>
  $GITHUB_OUTPUT` appends a `key=value` line to a special file GitHub Actions watches — that's the
  literal mechanism, not magic. Readable afterward as `steps.build-image.outputs.image`.

## Job 2, part 2: the actual ECS deploy

```yaml
    - name: Download current task definition
      run: |
        aws ecs describe-task-definition \
          --task-definition gha-test-repo-task \
          --query taskDefinition \
          --region $AWS_REGION > task-definition.json
    - name: Render new task definition with the new image
      id: render-task-def
      uses: aws-actions/amazon-ecs-render-task-definition@v1
      with:
        task-definition: task-definition.json
        container-name: flask-app
        image: ${{ steps.build-image.outputs.image }}
    - name: Deploy new task definition revision to ECS service
      uses: aws-actions/amazon-ecs-deploy-task-definition@v2
      with:
        task-definition: ${{ steps.render-task-def.outputs.task-definition }}
        service: gha-test-repo-service
        cluster: gha-test-repo-cluster
        wait-for-service-stability: true
```

The same three-step dance you'd do by hand, automated:

1. **Download current task definition** — pulls the *current* live Task Definition (whatever
   revision it's on) as JSON. Keeps every existing field (CPU/memory, env vars, secrets, network
   mode, IAM roles...) intact — only the image needs to change.
2. **Render new task definition** — finds the container named `flask-app` inside that JSON and
   swaps only its `image:` field to the new git-SHA-tagged image from `build-image`'s output.
   Doesn't register anything yet — just produces a *new* JSON blob as its own output
   (`steps.render-task-def.outputs.task-definition`).
3. **Deploy new task definition revision to ECS service** — actually calls `RegisterTaskDefinition`
   (creating a brand-new revision, e.g. `:8` if currently on `:7`) and updates the ECS service to
   point at it. `wait-for-service-stability: true` makes this step **block** until ECS confirms
   the new tasks are healthy and steady-state — if the new image crash-loops, this step fails
   loudly instead of reporting success while production is actually down.

This is why every deploy creates a *new* task definition revision instead of overwriting one —
full rollback history for free, each revision immutable once created.

## Do you have to memorize all of this?

No — and real DevOps engineers don't carry this file's exact syntax in their head either. What's
worth actually memorizing is the **mental model**, not the YAML spelling:

- Jobs are isolated VMs; steps within a job share state via `id:` + outputs.
- `uses:` calls someone else's packaged action; `run:` is your own shell command.
- Secrets live outside the file, injected at runtime.
- `needs:` chains jobs; `if:` gates them.
- A handful of official/common actions come up constantly: `actions/checkout`,
  `aws-actions/configure-aws-credentials`, `aws-actions/amazon-ecr-login`,
  `aws-actions/amazon-ecs-render-task-definition`, `aws-actions/amazon-ecs-deploy-task-definition`.

The exact `with:` field names, exact context syntax (`github.sha` vs `github.event_name`), exact
action versions — that's reference material. In practice, engineers:
- **Reuse and adapt working examples** — this file itself becomes the template for the next repo
  that needs the same ECS deploy pattern (already reflected in `COMMANDS.md`'s role here), rather
  than being retyped from memory.
- **Look up the action's README on the Marketplace** for its exact `with:` inputs/outputs — the
  actions used above all publish theirs.
- **Rely on the official GitHub Actions docs** for the underlying syntax (contexts, expressions,
  `GITHUB_OUTPUT`, path filters).
- **Lean on editor tooling** — YAML schema validation/autocomplete in VS Code catches typos in
  keys before a push ever wastes a CI run.

The skill that actually matters is being able to **read** an unfamiliar workflow file and
correctly explain what triggers it, what order things run in, and where a failure would occur —
not reproducing one from a blank file with no reference open.
