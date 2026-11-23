#!/bin/sh
# PostgreSQL backup for docker-compose.prod.yml (the backup service).
#
#   pg_backup.sh loop     - a snapshot right away and then every BACKUP_INTERVAL_HOURS hours (default)
#   pg_backup.sh once     - one snapshot
#   pg_backup.sh verify   - restore the latest snapshot into a temporary database and check it
#   pg_backup.sh restore FILE - restore a snapshot into the working database (stop api and worker first!)
#
# Snapshots are pg_dump in custom format (compressed, restored selectively and in parallel by pg_restore),
# named regence_YYYYmmdd_HHMMSS.dump. The file is written to a temporary name and renamed only after
# a successful pg_dump: an interrupted snapshot never looks complete. Snapshots older than
# BACKUP_KEEP_DAYS days are deleted.
#
# In loop mode, once every BACKUP_VERIFY_EVERY_DAYS days (7; 0 - off) a restore check is started after the snapshot.
# A failure of the snapshot or the check is written to the log as an "ERROR" line and, if BACKUP_ALERT_WEBHOOK_URL is set,
# sent as a POST request with text (Slack/Telegram bridge/any receiver). The time of the last check is the file
# .last_verify in BACKUP_DIR. The off-server copy of snapshots is a separate backup-offsite service (DEPLOY, section 5).
#
# Variables: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, PGHOST (db), BACKUP_DIR (/backups),
# BACKUP_INTERVAL_HOURS (24), BACKUP_KEEP_DAYS (14), BACKUP_VERIFY_EVERY_DAYS (7), BACKUP_ALERT_WEBHOOK_URL.
set -eu

: "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}" "${POSTGRES_DB:?}"
export PGHOST="${PGHOST:-db}" PGUSER="$POSTGRES_USER" PGPASSWORD="$POSTGRES_PASSWORD"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
VERIFY_EVERY_DAYS="${BACKUP_VERIFY_EVERY_DAYS:-7}"
ALERT_URL="${BACKUP_ALERT_WEBHOOK_URL:-}"
VERIFY_STAMP="$BACKUP_DIR/.last_verify"
CHECK_DB="${POSTGRES_DB}_restore_check"

log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') backup: $*"; }

# Failure alert: a line in the log always, a POST to the webhook if it is set. A failure of the alert itself
# must not bring down the schedule, so its error is only written to the log.
alert() {
    log "ERROR: $*"
    [ -n "$ALERT_URL" ] || return 0
    wget -q -T 10 -O /dev/null --post-data "regence backup: $*" "$ALERT_URL"         || log "WARNING: alert webhook is unreachable"
}

wait_for_db() {
    until pg_isready -q -d "$POSTGRES_DB"; do sleep 2; done
}

latest_backup() {
    ls -1 "$BACKUP_DIR"/regence_*.dump 2>/dev/null | sort | tail -n 1
}

backup_once() {
    mkdir -p "$BACKUP_DIR"
    target="$BACKUP_DIR/regence_$(date -u '+%Y%m%d_%H%M%S').dump"
    tmp="$target.partial"
    if pg_dump -Fc -d "$POSTGRES_DB" -f "$tmp"; then
        mv "$tmp" "$target"
        log "snapshot $(basename "$target") ($(du -h "$target" | cut -f1))"
    else
        rm -f "$tmp"
        alert "pg_dump failed"
        return 1
    fi
    find "$BACKUP_DIR" -name 'regence_*.dump' -type f -mtime +"$KEEP_DAYS" -print -delete \
        | sed 's/^/removed old snapshot /'
    find "$BACKUP_DIR" -name '*.partial' -type f -mmin +60 -delete
}

# A snapshot that cannot be restored is worse than no snapshot: the problem is discovered on the day of an outage.
verify_latest() {
    file="$(latest_backup)"
    [ -n "$file" ] || { alert "no snapshots in $BACKUP_DIR"; return 1; }
    psql -q -d postgres -c "DROP DATABASE IF EXISTS \"$CHECK_DB\"" -c "CREATE DATABASE \"$CHECK_DB\""
    status=0
    if pg_restore --no-owner -d "$CHECK_DB" "$file"; then
        summary="$(psql -At -d "$CHECK_DB" -c \
            "SELECT (SELECT version_num FROM alembic_version) || ' users=' || (SELECT count(*) FROM users)
                    || ' games=' || (SELECT count(*) FROM games)")" || status=1
        [ "$status" -eq 0 ] && log "verified $(basename "$file"): revision $summary"
    else
        status=1
    fi
    psql -q -d postgres -c "DROP DATABASE IF EXISTS \"$CHECK_DB\""
    [ "$status" -eq 0 ] || alert "snapshot $(basename "$file") failed to restore"
    return "$status"
}

# Scheduled check: not more often than once every VERIFY_EVERY_DAYS days. The timestamp is set on failure too,
# so that a broken snapshot does not raise an alarm after every snapshot but once per period.
verify_if_due() {
    [ "$VERIFY_EVERY_DAYS" -gt 0 ] || return 0
    if [ -f "$VERIFY_STAMP" ] && [ -z "$(find "$VERIFY_STAMP" -mtime +"$((VERIFY_EVERY_DAYS - 1))" 2>/dev/null)" ]; then
        return 0
    fi
    verify_latest || true
    touch "$VERIFY_STAMP"
}

restore() {
    file="$1"
    [ -f "$file" ] || file="$BACKUP_DIR/$1"
    [ -f "$file" ] || { log "ERROR: snapshot $1 not found"; return 1; }
    log "restoring $(basename "$file") into $POSTGRES_DB"
    pg_restore --clean --if-exists --no-owner --single-transaction -d "$POSTGRES_DB" "$file"
    log "restore finished"
}

case "${1:-loop}" in
    once)
        wait_for_db
        backup_once
        ;;
    verify)
        wait_for_db
        verify_latest
        ;;
    restore)
        [ $# -ge 2 ] || { echo "usage: $0 restore FILE" >&2; exit 2; }
        wait_for_db
        restore "$2"
        ;;
    loop)
        wait_for_db
        log "every ${INTERVAL_HOURS}h into $BACKUP_DIR, keeping ${KEEP_DAYS} days"
        while true; do
            # A failure of one snapshot does not stop the schedule: the next attempt is after the interval.
            backup_once || true
            verify_if_due
            sleep "$((INTERVAL_HOURS * 3600))"
        done
        ;;
    *)
        echo "usage: $0 [loop|once|verify|restore FILE]" >&2
        exit 2
        ;;
esac
