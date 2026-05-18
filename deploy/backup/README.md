# Database Backup Service

The `backup` service in [docker-compose.yml](../docker-compose.yml) runs a daily
`mysqldump` against the `db` service and writes a gzipped dump to a host
directory.

## Files

- [Dockerfile](Dockerfile) — based on `mysql:8.4` (so `mysqldump` is available)
- [backup.sh](backup.sh) — sleep loop that triggers a dump at the configured hour

## Environment variables

| Variable             | Default        | Notes                                                 |
|----------------------|----------------|-------------------------------------------------------|
| `MYSQL_HOST`         | `db`           | Service name on the docker network                    |
| `MYSQL_PORT`         | `3306`         |                                                       |
| `MYSQL_DATABASE`     | (required)     | Same as auth/admin services                           |
| `MYSQL_USER`         | (required)     |                                                       |
| `MYSQL_PASSWORD`     | (required)     |                                                       |
| `BACKUP_RETAIN_DAYS` | `30`           | Files older than this are deleted after each run      |
| `BACKUP_HOUR_UTC`    | `19`           | Dump runs once per day at this UTC hour (= 03:00 CST) |
| `BACKUP_ON_START`    | `0`            | Set to `1` to dump immediately on container start     |
| `BACKUP_HOST_DIR`    | `./_backups`   | Host path mounted to `/backups` inside container      |

`BACKUP_HOST_DIR` is consumed by `docker-compose.yml`, not the script. Set it in
your `.env` to put backups on a separate disk, e.g. `/srv/fms-backups`.

## Output

Files look like `fms_20260518_190005.sql.gz`. Restore with:

```bash
gunzip -c fms_20260518_190005.sql.gz | mysql -u<user> -p <database>
```

## Operations

```bash
# Manual immediate dump (one-off, runs in a fresh container, exits when done):
docker compose run --rm -e BACKUP_ON_START=1 backup sh -c \
  '/usr/local/bin/backup.sh & sleep 60; kill %1'

# Or simpler — exec into the running container and call the function via
# `dump_once`. Easiest: just wait for next scheduled run.

# View logs:
docker compose logs -f backup
```

## Notes

- `mysqldump --single-transaction` keeps the dump consistent without locking.
- `--set-gtid-purged=OFF` avoids embedding GTID state in the dump (safe to
  restore on any server).
- The script doesn't compress in-place with a partial filename rename, so an
  interrupted run leaves a `.partial` file that the next iteration ignores.
- For off-site copies, mount `/backups` somewhere your existing rsync /
  S3-uploader job already watches.
