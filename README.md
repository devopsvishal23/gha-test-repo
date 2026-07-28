# Docker Practice App — Flask + PostgreSQL

A small containerized CRUD app: a Flask web frontend backed by a PostgreSQL
database, wired together with a Dockerfile and Docker Compose. Used to
practice multi-container Docker setups (app + db), health checks, and
service dependencies.

## Project structure

```
.
├── app.py               # Flask application (routes, DB access)
├── requirements.txt     # Python dependencies
├── dockerfile            # Image definition for the web service
├── docker-compose.yml   # Orchestrates the web + db containers
└── templates/
    └── index.html        # Single page UI (list, add, delete records)
```

## How the code works

### `app.py`

- **Config** — DB connection settings are read from environment variables
  (`DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`), each with a local
  default so it can technically run without Docker too.
- **`wait_for_db()`** — on startup, retries connecting to Postgres (up to
  30 times, 1s apart) before giving up. This exists because the `web`
  container can start before Postgres is ready to accept connections.
- **`init_db()`** — creates the `records` table (`id`, `name`, `email`) if
  it doesn't already exist. Runs once at startup.
- **Routes:**
  | Route | Method | Purpose |
  |---|---|---|
  | `/health` | GET | Returns `200 {"status": "ok"}` if the DB is reachable, else `503`. Used by the Docker healthcheck. |
  | `/` | GET | Lists all records, newest first. |
  | `/add` | POST | Inserts a record from form fields `name` and `email`, then redirects to `/`. |
  | `/delete/<id>` | GET | Deletes a record by id, then redirects to `/`. |

- The app runs with Flask's built-in dev server (`app.run(..., debug=True)`)
  on `0.0.0.0:5000` — fine for practice, not for production.

### `templates/index.html`

A single Jinja2 template: a form that POSTs to `/add`, and a table of
existing records with a delete link per row. No JS — everything is plain
form submissions and server-side redirects.

### `dockerfile`

Builds the `web` image:
1. `python:3.11-slim` base image.
2. Installs dependencies from `requirements.txt` (layer cached separately
   from app code, so code changes don't bust the pip-install cache).
3. Copies the app code in.
4. Exposes port `5000`.
5. Declares a `HEALTHCHECK` that hits `/health` every 10s.
6. Runs `python app.py`.

### `docker-compose.yml`

Defines two services:
- **`web`** — built from the local `dockerfile`, exposed on host port
  `5000`, with DB env vars set to match the `db` service. It waits for
  `db` to report `service_healthy` before starting (`depends_on.condition`).
- **`db`** — official `postgres:15-alpine` image, exposed on host port
  `5432`, with a named volume (`pgdata`) so data survives container
  restarts/recreation. Healthcheck uses `pg_isready`.

Because `web` waits on `db`'s healthcheck, and `app.py` *also* retries the
connection itself, startup is doubly safe against race conditions.

## Prerequisites

- Docker Desktop (or Docker Engine) with Compose v2 — verify with:
  ```bash
  docker --version
  docker compose version
  ```

## Running it

From this directory (`practice-projects/`):

### Option A — Docker Compose (recommended)

Build the images and start both containers:

```bash
docker compose build
docker compose up -d
```

Check status:

```bash
docker compose ps
```

Open the app: **http://localhost:5000**

View logs:

```bash
docker compose logs -f web
```

Stop and remove containers (keeps the `pgdata` volume, so your data
persists):

```bash
docker compose down
```

Stop and also wipe the database volume:

```bash
docker compose down -v
```

### Option B — Build/run the image manually (no Compose)

Useful if you want to build just the `web` image or run it against a
DB you manage separately.

```bash
# Build
docker build -t docker-practice-app -f dockerfile .

# Run a Postgres container first (if you don't have one)
docker run -d --name practice-db \
  -e POSTGRES_DB=testdb \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:15-alpine

# Run the app, pointing it at that Postgres container
docker run -d --name practice-web \
  --link practice-db:db \
  -e DB_HOST=db \
  -e DB_NAME=testdb \
  -e DB_USER=postgres \
  -e DB_PASSWORD=postgres \
  -p 5000:5000 \
  docker-practice-app
```

(`--link` is legacy; prefer a user-defined network with `docker network
create` + `--network` if you're doing this outside Compose regularly.)

## Using the app

1. Visit `http://localhost:5000`.
2. Fill in **Name** and **Email**, click **Add** — inserts a row and
   reloads the list.
3. Click **Delete** next to any row to remove it.
4. `GET /health` returns `{"status": "ok"}` when the DB is reachable, or
   HTTP 503 with `{"status": "db unreachable"}` otherwise — useful for
   scripting a readiness check:
   ```bash
   curl http://localhost:5000/health
   ```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DB_HOST` | `db` | Postgres hostname |
| `DB_NAME` | `testdb` | Database name |
| `DB_USER` | `postgres` | Database user |
| `DB_PASSWORD` | `postgres` | Database password |

Set in `docker-compose.yml` under `services.web.environment`, and must
match the `db` service's `POSTGRES_*` settings.

## Troubleshooting

- **`web` keeps restarting / can't reach db** — check `docker compose logs db`
  and `docker compose logs web`. `wait_for_db()` gives up after ~30s; if
  Postgres takes longer to initialize (e.g. slow disk), increase `retries`
  in `app.py`.
- **Port already in use** — something else is bound to `5000` or `5432`
  locally. Either stop that process or change the host-side port mapping
  in `docker-compose.yml` (e.g. `"5001:5000"`).
- **Data disappeared after `docker compose down`** — that's expected if you
  used `-v` (removes volumes). Use plain `docker compose down` to keep the
  `pgdata` volume.
- **Code changes not showing up** — the image bakes in the app code at
  build time; after editing `app.py` or `templates/index.html`, rebuild
  with `docker compose up -d --build`.

## Verified

This setup was built and run end-to-end (`docker compose build`, `up`,
health check, add, list, delete, `down`) to confirm it works as
documented.
