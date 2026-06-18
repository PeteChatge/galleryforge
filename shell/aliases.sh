#!/usr/bin/env bash
# GalleryForge – Shell Aliases
#
# Canonical file: shell/aliases.sh
# Repo root wrapper: .gf_aliases  (sources this file – kept for Termux compat)
#
# Install (once per platform):
#   WSL2:   echo 'source ~/galleryforge/shell/aliases.sh' >> ~/.bashrc
#   Termux: echo 'source ~/galleryforge/.gf_aliases'      >> ~/.bashrc
#
# Platform detection: WSL2 / Termux / native Linux
# ──────────────────────────────────────────────────────────────────────────────

# ── Platform & Path Detection ─────────────────────────────────────────────────
if [ -n "$TERMUX_VERSION" ]; then
    # Android / Termux – data lives in Termux home, no Windows mounts
    GF_ROOT="$HOME/galleryforge/galleryforge"   # existing double-path on device
    GF_BASE="$HOME/___memubot"
else
    # WSL2 / native Linux
    GF_ROOT="$HOME/galleryforge"
    GF_BASE="/mnt/d/___memubot"
fi

export GF_ROOT GF_BASE
export GF_ASSETS="$GF_BASE/assets"
export GF_DATA="$GF_BASE/data"
export GF_RELEASES="$GF_BASE/releases"
export GF_LOGS="$GF_BASE/logs"
export GF_DB="$GF_DATA/galleryforge.db"

# ── Navigation ────────────────────────────────────────────────────────────────
alias gf='cd "$GF_ROOT" && source .venv/bin/activate'
alias gfcd='cd "$GF_ROOT"'
alias gfassets='cd "$GF_ASSETS"'
alias gfdata='cd "$GF_DATA"'
alias gfreleases='cd "$GF_RELEASES"'
alias gflogs='cd "$GF_LOGS"'

# ── venv ──────────────────────────────────────────────────────────────────────
alias gfvenv='source "$GF_ROOT/.venv/bin/activate"'

# ── Database ──────────────────────────────────────────────────────────────────
alias gfdb='sqlite3 "$GF_DB"'
alias gfassetsql='sqlite3 "$GF_DB" "SELECT id, filename, status FROM assets ORDER BY id DESC;"'
alias gfschema='sqlite3 "$GF_DB" ".schema assets"'

# ── Core Modules ──────────────────────────────────────────────────────────────
alias gfscan='python -m core.scanner'
alias gfdescribe='python -m core.describer'
alias gfrelease='python -m core.release_manager'
alias gfprocess='python -m core.process_new_assets'
alias gfbuild='python -m core.gallery_builder'
alias gfstats='python -m core.stats'
alias gfwatch='python -m core.watcher'
alias gfconfig='python -m core.config_loader'
alias gflogger='python -m core.logger'
alias gfregistry='python -m core.asset_registry'

# ── Workflows (Pipelines) ─────────────────────────────────────────────────────
# Standard full pipeline: scan → describe → release → process → build → stats
alias gffull='gfscan && gfdescribe && gfrelease && gfprocess && gfbuild && gfstats'

# Post-release update: process new assets, rebuild gallery, show stats
alias gfnewup='gfprocess && gfbuild && gfstats'

# ── Git ───────────────────────────────────────────────────────────────────────
alias gfstatus='git -C "$GF_ROOT" status'
alias gfpull='git -C "$GF_ROOT" pull'
alias gfpush='git -C "$GF_ROOT" push'
alias gfsave='git -C "$GF_ROOT" add . && git -C "$GF_ROOT" commit -m'
alias gfsync='git -C "$GF_ROOT" add . && git -C "$GF_ROOT" commit -m "sync" && git -C "$GF_ROOT" push'
alias gfhistory='git -C "$GF_ROOT" log --oneline --graph --decorate --all'
alias gflog='git -C "$GF_ROOT" log --oneline --graph --decorate'

# ── Init (create data folder structure) ──────────────────────────────────────
alias gfinit='mkdir -p "$GF_BASE"/{assets/{archive,inbox,processed,rejected,thumbnails},backups,data,docker,logs,models,releases/staging,temp} && echo "GalleryForge folders created under $GF_BASE"'

# ── Misc ──────────────────────────────────────────────────────────────────────
alias gftree='find "$GF_ROOT" -maxdepth 2 -type f | sort'
