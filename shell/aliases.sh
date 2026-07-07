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
# GalleryForge Root
export GF_ROOT="$HOME/galleryforge"

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
alias gfdiff='git -C "$GF_ROOT" diff'
alias gfbranch='git -C "GF_ROOT" branch'
alias gfgraph='git -C "$GF_ROOT" log --graph --decorate --oneline --all'


# ── Init (create data folder structure) ──────────────────────────────────────
alias gfinit='mkdir -p "$GF_BASE"/{assets/{archive,inbox,processed,rejected,thumbnails},backups,data,docker,logs,models,releases/staging,temp} && echo "GalleryForge folders created under $GF_BASE"'

# ── Misc ──────────────────────────────────────────────────────────────────────
alias gftree='find "$GF_ROOT" -maxdepth 2 -type f | sort'
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
# ALIASES FUER DEN LOOPER
# ende="curl -X POST http://192.168.1.131:18188/interrupt"
# ende-hart="curl -X POST http://192.168.1.131:18188/interrupt && curl -X POST http://192.168.1.131:18188/queue -H" "Content-Type: application/json" -d "{\"clear\": true}"'
# hardend="curl -X POST http://192.168.1.131:18188/interrupt && curl -X POST http://192.168.1.131:18188/queue" -H "Content-Type: application/json" -d "{\"clear\": true}"'
# clearam="curl -X POST http://192.168.1.131:18188/free -H "Content-Type: application/json" -d '{"unload_models": true, "free_memory": true}'"
# VRAM manuell freigeben (wan_circle.py macht das inzwischen automatisch vor/nach dem Loop)
vram-frei='curl -X POST http://192.168.1.131:18188/free -H "Content-Type: application/json" -d "{\"unload_models\": true, \"free_memory\": true}"'
vramfree='curl -X POST http://192.168.1.131:18188/free -H "Content-Type: application/json" -d "{\"unload_models\": true, \"free_memory\": true}"'
### ====== LOOPER (WAN2.2 Circle-Loop) ======

# Variante A: fester Alias mit Standard-Pfaden: /mnt/c/Users/Olaf/Downloads/loop-files/startbild.png UND prompts.csv
# startbild.png und prompts.csv müssen genau SO benannt werden!
loop='cd ~/looper && source venv/bin/activate && python3 wan_circle.py --start-image /mnt/c/Users/Olaf/Downloads/loop-files/startbild.png --prompts /mnt/c/Users/Olaf/Downloads/loop-files/prompts.csv --filename-prefix loopclip'

# Variante B: Funktion mit optionalen Parametern (Startbild, Prompts-CSV, Filename-Prefix)
# Nutzung:
#   loopf                                          -> alle Defaults
#   loopf /pfad/anderes_bild.png                   -> eigenes Startbild, Rest Default
#   loopf /pfad/bild.png prompts/clip2.csv clip2   -> alles individuell
loopf() {
  local startbild="${1:-/mnt/c/Users/Olaf/Downloads/loop-files/startbild.png}"
  local promptcsv="${2:-prompts/prompts.csv}"
  local prefix="${3:-loopclip}"
  (cd ~/looper && source venv/bin/activate && python3 wan_circle.py \
    --start-image "$startbild" \
    --prompts "$promptcsv" \
    --filename-prefix "$prefix")
}

# Laufenden Sampling-Schritt in ComfyUI abbrechen (Skript selbst danach per Strg+C beenden)
ende='curl -X POST http://192.168.1.131:18188/interrupt'

# Wie "ende", aber leert zusaetzlich die Warteschlange
ende-hart='curl -X POST http://192.168.1.131:18188/interrupt && curl -X POST http://192.168.1.131:18188/queue -H "Content-Type: application/json" -d "{\"clear\": true}"'
