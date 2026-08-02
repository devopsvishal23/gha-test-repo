# Command Reference — gha-test-repo

A running cheatsheet of commands used (or useful) while taking this app from local Docker to
production on AWS ECS. Add to this as new commands come up — this is meant to be the thing you
reach for during blind practice instead of digging through chat history.

## Local Docker / Compose

```bash
# Check tooling is installed
docker --version
docker compose version

# Build images defined in docker-compose.yml
docker compose build

# Start both containers (web + db) in the background
docker compose up -d

# Rebuild the image and restart (use after editing app.py / templates)
docker compose up -d --build

# See container status
docker compose ps

# Follow logs for one service
docker compose logs -f web
docker compose logs -f db

# Stop containers, KEEP the pgdata volume (data survives)
docker compose down

# Stop containers AND wipe the pgdata volume (data lost)
docker compose down -v

# Hit the health endpoint manually
curl http://localhost:5000/health
```

Build/run the image manually, without Compose (e.g. to test just the `web` image):

```bash
docker build -t docker-practice-app -f dockerfile .

docker run -d --name practice-db \
  -e POSTGRES_DB=testdb \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:15-alpine

docker run -d --name practice-web \
  --link practice-db:db \
  -e DB_HOST=db -e DB_NAME=testdb -e DB_USER=postgres -e DB_PASSWORD=postgres \
  -p 5000:5000 \
  docker-practice-app
```

## Git / GitHub

```bash
# Check what's changed before committing
git status
git diff

# Stage, commit, push (this repo's CI/CD fires on every push to main)
git add <file>
git commit -m "message"
git push

# Check recent history / where a change landed
git log --oneline -10

# Watch the GitHub Actions run triggered by your push
gh run list --limit 5
gh run watch          # follow the most recent run live
gh run view --log-failed   # inspect why a run failed
```

## AWS CLI — ECS (cluster: `gha-test-repo-cluster`, service: `gha-test-repo-service`)

```bash
# Force the service to redeploy the latest image (what CI/CD runs automatically)
aws ecs update-service \
  --cluster gha-test-repo-cluster \
  --service gha-test-repo-service \
  --force-new-deployment \
  --region us-east-2

# Check service status — running/desired count, deployment state
aws ecs describe-services \
  --cluster gha-test-repo-cluster \
  --services gha-test-repo-service \
  --region us-east-2

# List running tasks for the service
aws ecs list-tasks \
  --cluster gha-test-repo-cluster \
  --service-name gha-test-repo-service \
  --region us-east-2

# Inspect a specific task (health status, which task def revision it's running)
aws ecs describe-tasks \
  --cluster gha-test-repo-cluster \
  --tasks <task-arn> \
  --region us-east-2

# View the current (or a specific) Task Definition revision
aws ecs describe-task-definition \
  --task-definition gha-test-repo-task \
  --region us-east-2
```

## AWS CLI — ECR (repo: `gha-test-repo-app`)

```bash
# List pushed image tags
aws ecr describe-images \
  --repository-name gha-test-repo-app \
  --region us-east-2

# Log in Docker to ECR (needed only if pushing/pulling manually, not via CI)
aws ecr get-login-password --region us-east-2 \
  | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-2.amazonaws.com
```

## AWS CLI — RDS (instance: `gha-test-repo-db`)

```bash
# Check instance status / endpoint
aws rds describe-db-instances \
  --db-instance-identifier gha-test-repo-db \
  --region us-east-2
```

## Misc

```bash
# Generate a real random value for SECRET_KEY (never use the dev fallback in prod)
openssl rand -hex 32
```
</content>
