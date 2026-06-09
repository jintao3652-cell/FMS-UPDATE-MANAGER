# Database Migrations (alembic)

backup_auth and admin_panel share a **single MySQL database**. All schema
changes flow through alembic in **this** service (`deploy/backup_auth/`).
admin_panel does NOT run alembic separately.

## Layout

```
deploy/backup_auth/
  alembic.ini              # alembic config (sqlalchemy.url comes from APP_DB_URL at runtime)
  alembic/
    env.py                 # loads Base from app.models, reads APP_DB_URL
    script.py.mako         # template for new revisions
    versions/
      0001_baseline.py     # creates the full v1.0.6 schema (idempotent)
```

## How upgrades run in production

`docker-compose.yml` runs the backup_auth container's startup with
`alembic upgrade head` *before* uvicorn boots. Old-style
`Base.metadata.create_all` and `ensure_schema_compat` still run as a safety
net for ad-hoc setups, but `alembic upgrade head` is the source of truth.

## Initial migration on a pre-existing v1.0.5 DB

If you are upgrading an already-running deployment, alembic must believe the
baseline migration is "already applied":

```bash
docker compose run --rm auth_api alembic stamp head
```

After that, future schema changes go through:

```bash
docker compose run --rm auth_api alembic revision --autogenerate -m "add foo"
# review the generated file in alembic/versions/, then:
docker compose run --rm auth_api alembic upgrade head
```

`alembic stamp` does NOT modify your data; it just records that the baseline
revision is the current head in the `alembic_version` table.

## Authoring new migrations

1. Edit `app/models.py` (and any related `app/*.py`).
2. From `deploy/backup_auth/`, generate a revision skeleton:
   ```bash
   alembic revision --autogenerate -m "add my_table"
   ```
3. **Review the generated file.** Autogenerate misses index renames, server
   defaults, and JSON column type changes — fix those by hand.
4. Commit the file under `alembic/versions/`.
5. On deploy, `alembic upgrade head` brings prod to the new revision.

## Why both services don't run alembic

Two services concurrently `alembic upgrade head` race on the
`alembic_version` row and on `CREATE TABLE IF NOT EXISTS`. Pick a single
owner. backup_auth is the owner because it carries the bulk of the schema
(`users`, `crash_reports`, `email_outbox`, `cycle_*`, …); admin_panel only
adds the `admin_audit` view which is included in `0001_baseline.py`.
