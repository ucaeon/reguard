#!/bin/bash
set -Eeuo pipefail
umask 077
export PGCONNECT_TIMEOUT=15
export PGOPTIONS='-c statement_timeout=1800000 -c lock_timeout=30000'
backup_root=/backups
scratch=/scratch
exec 9> "$backup_root/.lock"
flock -n 9 || { echo "Another backup is already running" >&2; exit 75; }
run_id="$(date -u +%Y%m%dT%H%M%SZ)-${HOSTNAME}"
partial="$backup_root/.partial-$run_id"
mkdir -p "$partial" "$scratch/socket"

cleanup() {
  code=$?
  trap - EXIT
  if test -f "$scratch/db/postmaster.pid"; then
    pg_ctl -D "$scratch/db" -m immediate -w stop >/dev/null 2>&1 || true
  fi
  if ((code != 0)); then
    printf 'FAILED %s\n' "$run_id" >&2
    printf '%s\n' "$code" > "$partial/FAILED" 2>/dev/null || true
  fi
  exit "$code"
}
trap cleanup EXIT
initdb -D "$scratch/db" --auth-local=trust --auth-host=reject --no-instructions > "$scratch/init.log"
pg_ctl -D "$scratch/db" -l "$scratch/postgres.log" -o "-k $scratch/socket -p 55432 -c listen_addresses='' -c shared_buffers=64MB -c max_connections=10" -w start >/dev/null

count_query="SELECT format('SELECT %L,count(*) FROM %I.%I;',schemaname||'.'||tablename,schemaname,tablename) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname,tablename;"
backup_database() {
  local host=$1 database=$2 username=$3 password_key=$4 snapshot snapshot_pid
  export PGPASSWORD="${!password_key}"
  # Both pg_dump and the source counts use the same exported MVCC snapshot.
  coproc SNAPSHOT { psql -XqAt -v ON_ERROR_STOP=1 -h "$host" -U "$username" -d "$database"; }
  snapshot_pid=$SNAPSHOT_PID
  printf 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\nSELECT pg_export_snapshot();\n' >&"${SNAPSHOT[1]}"
  read -r snapshot <&"${SNAPSHOT[0]}"
  [[ "$snapshot" =~ ^[0-9A-Fa-f-]+$ ]] || { echo 'Invalid snapshot' >&2; return 1; }
  pg_dump -h "$host" -U "$username" -d "$database" --snapshot="$snapshot" -Fc --no-owner --no-acl -f "$partial/$database.dump"
  {
    printf "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\nSET TRANSACTION SNAPSHOT '%s';\n" "$snapshot"
    printf '%s\n\\gexec\nCOMMIT;\n' "${count_query%;}"
  } | psql -XqAt -v ON_ERROR_STOP=1 -h "$host" -U "$username" -d "$database" > "$partial/$database.source-counts"
  printf 'COMMIT;\n\\q\n' >&"${SNAPSHOT[1]}"
  wait "$snapshot_pid"
  unset PGPASSWORD
  createdb -h "$scratch/socket" -p 55432 "$database"
  pg_restore --exit-on-error --no-owner --no-acl -h "$scratch/socket" -p 55432 -d "$database" "$partial/$database.dump"
  printf '%s\n\\gexec\n' "${count_query%;}" | psql -XqAt -v ON_ERROR_STOP=1 -h "$scratch/socket" -p 55432 -d "$database" > "$partial/$database.restored-counts"
  test -s "$partial/$database.restored-counts"
  diff -u "$partial/$database.source-counts" "$partial/$database.restored-counts"
  (cd "$partial" && sha256sum "$database.dump") >> "$partial/SHA256SUMS"
  printf 'PASS restore %s: %s tables match source snapshot\n' "$database" "$(wc -l < "$partial/$database.restored-counts")"
  dropdb -h "$scratch/socket" -p 55432 "$database"
}

backup_database postgres reguard_member reguard_member MEMBER_DB_PASSWORD
backup_database postgres reguard_safety reguard_safety SAFETY_DB_PASSWORD
backup_database postgres reguard_notification reguard_notification NOTIFICATION_DB_PASSWORD
backup_database metadata airflow airflow AIRFLOW_DB_PASSWORD
(cd "$partial" && sha256sum --check SHA256SUMS)
printf 'verified_at=%s\ndatabases=4\nverification=snapshot-counts-and-full-restore\n' "$(date -u +%FT%TZ)" > "$partial/VERIFIED"
mv "$partial" "$backup_root/verified-$run_id"
# Expire only completed, verified sets after a newer complete set exists.
find "$backup_root" -mindepth 1 -maxdepth 1 -type d -name 'verified-*' -mmin +20160 -exec sh -c 'test -f "$1/VERIFIED" && rm -rf -- "$1"' sh {} \;
find "$backup_root" -mindepth 1 -maxdepth 1 -type d -name '.partial-*' -mmin +20160 -exec rm -rf -- {} \;
printf 'SUCCESS %s\n' "$run_id"
