#!/usr/bin/env bash
# Ubuntu 24.04. Run after uploading the project: sudo bash deploy/server.sh
set -Eeuo pipefail
umask 022
[[ $EUID == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
[[ $# == 0 || ( $# == 1 && $1 == --stop ) ]] || { echo 'Usage: server.sh [--stop]' >&2; exit 1; }
exec 9>/run/fnote-deploy.lock
flock -n 9 || { echo 'Another deployment is running.' >&2; exit 1; }
app=/opt/fnote
python=/opt/fnote-env/bin/python
site=/etc/caddy/fnote.caddy
stop_app() {
    for unit in fnote-cleanup.timer fnote-backup.timer fnote.service; do
        if systemctl cat "$unit" >/dev/null 2>&1; then systemctl disable --now "$unit"; fi
    done
    for unit in fnote-cleanup.service fnote-backup.service; do
        if systemctl cat "$unit" >/dev/null 2>&1; then systemctl stop "$unit"; fi
    done
}
if [[ ${1:-} == --stop ]]; then
    stop_app
    if [[ -f $site ]]; then
        rm -- "$site"
        caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
        if systemctl is-active --quiet caddy; then systemctl reload caddy; fi
    fi
    echo 'Stopped. Database, backups and certificates retained.'
    exit 0
fi
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || { echo 'Ubuntu 24.04 required.' >&2; exit 1; }
source_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
runtime="$app/runtime"
[[ -f $source_root/backend/scripts/local.py ]] || { echo 'Upload the complete project.' >&2; exit 1; }
[[ -f /var/lib/fnote/fnote.db || -f $source_root/backend/data/fnote.db ]] || {
    echo 'Missing migration database: backend/data/fnote.db. Stop the local application before uploading.' >&2; exit 1;
}
mkdir -p "$runtime"
trap 'echo "Deployment failed at line $LINENO. Inspect $runtime/server-error.log and $runtime/deploy.log; application may remain stopped." >&2' ERR
exec > >(tee -a "$runtime/deploy.log") 2>&1
# Check the installed release before interrupting a running service.
[[ -x $python && -f $app/backend/scripts/local.py && -f $app/frontend/dist/index.html ]] || {
    echo 'Installed application is incomplete. Run sudo bash deploy/setup.sh first.' >&2; exit 1;
}
command -v caddy >/dev/null || { echo 'Caddy is missing. Run deploy/setup.sh first.' >&2; exit 1; }
command -v logrotate >/dev/null || { echo 'logrotate is missing. Run deploy/setup.sh first.' >&2; exit 1; }
id fnote >/dev/null 2>&1 || { echo 'Service account is missing. Run deploy/setup.sh first.' >&2; exit 1; }
(cd "$app/backend" && "$python" -c 'import sys, sqlite3, fastapi, uvicorn, alembic, sqlalchemy, cryptography; assert sqlite3.sqlite_version_info >= (3,51,3)') || {
    echo 'Installed Python dependencies are invalid. Run deploy/setup.sh first.' >&2; exit 1;
}
key="$app/runtime/secrets/ai-config.key"
uploaded_key="$source_root/runtime/secrets/ai-config.key"
if [[ $source_root != "$app" && -f $uploaded_key && -f $key ]]; then
    cmp -s "$uploaded_key" "$key" || { echo 'Uploaded master key differs from the deployed key.' >&2; exit 1; }
fi
stop_app
install -d -o fnote -g fnote -m 750 /var/lib/fnote /var/lib/fnote/runtime /var/backups/fnote
install -d -o fnote -g fnote -m 750 "$app/runtime"
runtime_pattern=$(printf '%s' "$runtime" | sed 's/[\\&|]/\\&/g')
sed "s|@RUNTIME@|$runtime_pattern|g" "$source_root/deploy/fnote.logrotate" > /etc/logrotate.d/fnote
chown root:root /etc/logrotate.d/fnote
chmod 644 /etc/logrotate.d/fnote
systemctl enable --now logrotate.timer
cat > /etc/fnote.env <<'ENV'
FNOTE_DATABASE=/var/lib/fnote/fnote.db
FNOTE_RUNTIME=/var/lib/fnote/runtime
FNOTE_BACKUPS=/var/backups/fnote
APP_ORIGIN=https://uuuf.online
COOKIE_SECURE=true
ENV
chmod 640 /etc/fnote.env
chown root:fnote /etc/fnote.env
run_app() {
    (set -a; source /etc/fnote.env; set +a; cd "$app/backend"; runuser -u fnote -- "$python" -m scripts.local "$@")
}
if [[ ! -f /var/lib/fnote/fnote.db ]]; then
    # Online import preserves committed WAL contents if the uploaded sidecars exist.
    # Copy into a private staging directory readable by the service user.
    import_dir=$(mktemp -d /var/lib/fnote/import.XXXXXXXX)
    cp -- "$source_root/backend/data/fnote.db" "$import_dir/fnote.db"
    for suffix in -wal -shm; do
        if [[ -f $source_root/backend/data/fnote.db$suffix ]]; then cp -- "$source_root/backend/data/fnote.db$suffix" "$import_dir/fnote.db$suffix"; fi
    done
    chown -R fnote:fnote "$import_dir"
    run_app import --source "$import_dir/fnote.db"
    rm -f -- "$import_dir/fnote.db" "$import_dir/fnote.db-wal" "$import_dir/fnote.db-shm"
    rmdir -- "$import_dir"
fi
install -d -o fnote -g fnote -m 700 "$app/runtime/secrets"
key="$app/runtime/secrets/ai-config.key"
uploaded_key="$source_root/runtime/secrets/ai-config.key"
if [[ $source_root != "$app" && -f $uploaded_key ]]; then
    if [[ -f $key ]]; then
        cmp -s "$uploaded_key" "$key" || { echo 'Uploaded master key differs from the deployed key; refusing to overwrite.' >&2; exit 1; }
    else
        install -o root -g fnote -m 640 "$uploaded_key" "$key"
    fi
fi
if [[ -f $key ]]; then
    chown root:fnote "$key"
    chmod 640 "$key"
fi
run_app prepare
chown root:fnote "$key"
chmod 640 "$key"
log_runtime=${runtime//%/%%}
cat > /etc/systemd/system/fnote.service <<UNIT
[Unit]
Description=FNote application
After=network.target
[Service]
User=fnote
Group=fnote
WorkingDirectory=/opt/fnote/backend
EnvironmentFile=/etc/fnote.env
ExecStart=/opt/fnote-env/bin/python -m scripts.local serve
StandardOutput=append:$log_runtime/server.log
StandardError=append:$log_runtime/server-error.log
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
UMask=0027
NoNewPrivileges=true
ProtectSystem=strict
PrivateTmp=true
ProtectHome=true
ReadWritePaths=/var/lib/fnote /var/backups/fnote /opt/fnote/runtime
[Install]
WantedBy=multi-user.target
UNIT
for job in cleanup backup; do
    operation='scripts.cleanup_workouts'
    at=03:00:00
    if [[ $job == backup ]]; then operation='scripts.local backup'; at=03:30:00; fi
    cat > "/etc/systemd/system/fnote-$job.service" <<UNIT
[Unit]
Description=FNote $job
[Service]
Type=oneshot
User=fnote
Group=fnote
WorkingDirectory=/opt/fnote/backend
EnvironmentFile=/etc/fnote.env
ExecStart=/opt/fnote-env/bin/python -m $operation
StandardOutput=append:$log_runtime/$job.log
StandardError=inherit
Environment=PYTHONUNBUFFERED=1
Environment=FNOTE_LOG_STDERR=1
UMask=0027
TimeoutStartSec=30min
NoNewPrivileges=true
ProtectSystem=strict
PrivateTmp=true
ProtectHome=true
ReadWritePaths=/var/lib/fnote /var/backups/fnote /opt/fnote/runtime
UNIT
    cat > "/etc/systemd/system/fnote-$job.timer" <<UNIT
[Unit]
Description=FNote daily $job (Beijing time)
[Timer]
OnCalendar=*-*-* $at Asia/Shanghai
Persistent=true
[Install]
WantedBy=timers.target
UNIT
done
systemctl daemon-reload
systemctl enable --now fnote.service
health_check() {
    local response
    response=$(curl -fsS --connect-timeout 2 --max-time 5 "$1" 2>/dev/null) || return 1
    printf '%s' "$response" | "$python" -c 'import sys,json; assert json.load(sys.stdin)["status"] == "ok"' 2>/dev/null
}
ready=false
for attempt in {1..40}; do
    if health_check http://127.0.0.1:8765/api/health; then ready=true; break; fi
    sleep 1
done
[[ $ready == true ]] || { systemctl disable --now fnote.service; echo 'Health check failed.' >&2; exit 1; }
mkdir -p /etc/caddy
if ! grep -qxF 'import /etc/caddy/fnote.caddy*' /etc/caddy/Caddyfile; then
    printf '\nimport /etc/caddy/fnote.caddy*\n' >> /etc/caddy/Caddyfile
fi
cat > "$site" <<'CADDY'
uuuf.online {
    reverse_proxy 127.0.0.1:8765
}
CADDY
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl enable --now caddy
systemctl reload caddy
systemctl enable --now fnote-cleanup.timer fnote-backup.timer
echo 'Waiting up to 180 seconds for HTTPS readiness and initial certificate issuance...'
ready=false
deadline=$((SECONDS + 180))
while (( SECONDS < deadline )); do
    if health_check https://uuuf.online/api/health; then ready=true; break; fi
    if ! systemctl is-active --quiet caddy; then
        echo 'Caddy is not running.' >&2
        break
    fi
    sleep 3
done
if [[ $ready != true ]]; then
    echo 'HTTPS is not ready. Application and Caddy remain running; inspect certificate issuance, DNS and TCP 80/443, then retry the health URL.' >&2
    journalctl -u caddy -n 40 --no-pager >&2 || true
    exit 1
fi
echo 'Deployed: https://uuuf.online. Stop: sudo bash deploy/server.sh --stop'
