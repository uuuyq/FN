#!/usr/bin/env bash
# Ubuntu 24.04. Install/update the release, then run deploy/server.sh.
set -Eeuo pipefail
umask 022
[[ $EUID == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
[[ $# == 0 ]] || { echo 'Usage: setup.sh' >&2; exit 1; }
exec 9>/run/fnote-deploy.lock
flock -n 9 || { echo 'Another deployment is running.' >&2; exit 1; }
app=/opt/fnote
python=/opt/fnote-env/bin/python
stop_app() {
    for unit in fnote-cleanup.timer fnote-backup.timer fnote.service; do
        if systemctl cat "$unit" >/dev/null 2>&1; then systemctl disable --now "$unit"; fi
    done
    for unit in fnote-cleanup.service fnote-backup.service; do
        if systemctl cat "$unit" >/dev/null 2>&1; then systemctl stop "$unit"; fi
    done
}
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || { echo 'Ubuntu 24.04 required.' >&2; exit 1; }
source_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
[[ -f $source_root/backend/scripts/local.py ]] || { echo 'Upload the complete project.' >&2; exit 1; }
trap 'echo "Deployment failed at line $LINENO. Inspect journalctl -u fnote and /var/log/fnote-deploy.log; application may remain stopped." >&2' ERR
exec > >(tee -a /var/log/fnote-deploy.log) 2>&1
download() {
    curl -fSL --connect-timeout 20 --max-time 300 --speed-limit 1024 --speed-time 60 \
        --retry 3 --retry-delay 3 --retry-all-errors "$1" -o "$2"
}
conda_channel=${FNOTE_CONDA_CHANNEL:-https://conda.anaconda.org/conda-forge}
pip_index=${FNOTE_PIP_INDEX:-https://pypi.org/simple}
npm_registry=${FNOTE_NPM_REGISTRY:-https://registry.npmjs.org}
apt-get update
apt-get install -y ca-certificates curl gnupg rsync bzip2
# Official Caddy package repository. Existing Caddy configuration is preserved.
if ! command -v caddy >/dev/null; then
    caddy_key=$(mktemp)
    download https://dl.cloudsmith.io/public/caddy/stable/gpg.key "$caddy_key"
    gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg "$caddy_key"
    rm -- "$caddy_key"
    download https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt /etc/apt/sources.list.d/caddy-stable.list
    apt-get update
    apt-get install -y caddy
fi
if [[ ! -x /opt/fnote-conda/bin/conda ]]; then
    arch=$(uname -m)
    [[ $arch == x86_64 || $arch == aarch64 ]] || { echo 'Unsupported CPU architecture.' >&2; exit 1; }
    stage=$(mktemp -d)
    installer="Miniforge3-Linux-${arch}.sh"
    verify_installer() {
        local expected actual
        # Release checksums may name the versioned file rather than its latest alias.
        read -r expected _ < "$stage/$installer.sha256" || return 1
        [[ $expected =~ ^[[:xdigit:]]{64}$ ]] || return 1
        actual=$(sha256sum "$stage/$installer") || return 1
        [[ ${actual%% *} == "${expected,,}" ]]
    }
    ready=false
    if [[ -f $source_root/runtime/installers/$installer && -f $source_root/runtime/installers/$installer.sha256 ]]; then
        cp -- "$source_root/runtime/installers/$installer" "$source_root/runtime/installers/$installer.sha256" "$stage/"
        verify_installer || { echo 'Uploaded Miniforge checksum failed.' >&2; exit 1; }
        ready=true
    else
        # Use matching versioned assets; the unversioned installer alias has no checksum asset.
        release=26.9.4-2
        base=${FNOTE_MINIFORGE_BASE:-https://github.com/conda-forge/miniforge/releases/download/$release}
        asset="Miniforge3-${release}-Linux-${arch}.sh"
        echo "Downloading Miniforge from $base"
        if download "$base/$asset" "$stage/$installer" && \
           download "$base/$asset.sha256" "$stage/$installer.sha256" && verify_installer; then
            ready=true
        fi
    fi
    [[ $ready == true ]] || { echo "Cannot download Miniforge. Upload $installer and its .sha256 file to runtime/installers and retry." >&2; exit 1; }
    bash "$stage/$installer" -b -p /opt/fnote-conda
    rm -- "$stage/$installer" "$stage/$installer.sha256"
    rmdir -- "$stage"
fi
stop_app
conda_operation=create
if [[ -d /opt/fnote-env/conda-meta ]]; then conda_operation=install; fi
/opt/fnote-conda/bin/conda "$conda_operation" -y -p /opt/fnote-env --override-channels -c "$conda_channel" 'python=3.12' 'sqlite>=3.51.3' 'nodejs=22' 'pnpm=10' pip
"$python" -c 'import sqlite3; assert sqlite3.sqlite_version_info >= (3,51,3), sqlite3.sqlite_version'
id fnote >/dev/null 2>&1 || useradd --system --home-dir /var/lib/fnote --shell /usr/sbin/nologin fnote
install -d -o fnote -g fnote -m 750 /var/lib/fnote /var/lib/fnote/runtime /var/backups/fnote
install -d -m 755 "$app"
if [[ $source_root != "$app" ]]; then
    rsync -a --exclude=.git --exclude=node_modules --exclude=.venv --exclude=runtime --exclude=__pycache__ --exclude='*.db*' --exclude=.env "$source_root/" "$app/"
fi
"$python" -m pip install --index-url "$pip_index" --retries 3 --timeout 60 -r "$app/requirements.txt"
export PATH="/opt/fnote-env/bin:$PATH"
(cd "$app/frontend" && pnpm install --registry "$npm_registry" --frozen-lockfile && pnpm build)
chmod 755 "$app" "$app/frontend"
chmod -R a+rX "$app/backend" "$app/frontend/dist"

echo 'Installation complete. Start with: sudo bash deploy/server.sh'
