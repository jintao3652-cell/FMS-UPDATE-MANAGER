#!/bin/sh
# Daily mysqldump backup. Runs forever in a loop (managed by docker-compose restart).
# Dumps DB to /backups/fms_<YYYYMMDD_HHMMSS>.sql.gz at BACKUP_HOUR_UTC every day.
# Retains BACKUP_RETAIN_DAYS days of files.

set -eu

: "${MYSQL_HOST:=db}"
: "${MYSQL_PORT:=3306}"
: "${MYSQL_DATABASE:?MYSQL_DATABASE required}"
: "${MYSQL_USER:?MYSQL_USER required}"
: "${MYSQL_PASSWORD:?MYSQL_PASSWORD required}"
: "${BACKUP_RETAIN_DAYS:=30}"
: "${BACKUP_HOUR_UTC:=19}"   # 19:00 UTC = 03:00 Beijing
: "${BACKUP_DIR:=/backups}"

mkdir -p "$BACKUP_DIR"

dump_once() {
  ts="$(date -u +%Y%m%d_%H%M%S)"
  out="$BACKUP_DIR/fms_${ts}.sql.gz"
  tmp="$out.partial"
  echo "[backup] $(date -u +%FT%TZ) starting dump -> $out"
  if mysqldump \
        --host="$MYSQL_HOST" \
        --port="$MYSQL_PORT" \
        --user="$MYSQL_USER" \
        --password="$MYSQL_PASSWORD" \
        --single-transaction \
        --routines \
        --triggers \
        --events \
        --hex-blob \
        --default-character-set=utf8mb4 \
        --set-gtid-purged=OFF \
        "$MYSQL_DATABASE" \
      | gzip -9 > "$tmp"; then
    mv "$tmp" "$out"
    echo "[backup] $(date -u +%FT%TZ) ok: $(stat -c%s "$out" 2>/dev/null || wc -c < "$out") bytes"
  else
    rc=$?
    rm -f "$tmp"
    echo "[backup] $(date -u +%FT%TZ) FAILED rc=$rc"
    return $rc
  fi
}

prune() {
  find "$BACKUP_DIR" -maxdepth 1 -name 'fms_*.sql.gz' -mtime "+$BACKUP_RETAIN_DAYS" -print -delete || true
}

# Optional immediate dump on first boot if BACKUP_ON_START=1
if [ "${BACKUP_ON_START:-0}" = "1" ]; then
  dump_once || true
  prune || true
fi

while :; do
  now_h=$(date -u +%-H)
  now_m=$(date -u +%-M)
  target_h=$(echo "$BACKUP_HOUR_UTC" | sed 's/^0*//')
  : "${target_h:=0}"
  if [ "$now_h" -eq "$target_h" ] && [ "$now_m" -eq 0 ]; then
    dump_once || true
    prune || true
    # sleep enough to skip past this minute
    sleep 90
  else
    sleep 30
  fi
done
