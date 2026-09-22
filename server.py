#!/usr/bin/env python3
"""GalleryForge Web-Steuerung (Flask, Port 15001).

Start (WSL, CWD egal):  ~/galleryforge/.venv/bin/python ~/galleryforge/server.py
Aufruf:                  http://192.168.1.131:15001/   (via Portproxy ins WSL)

Routen:
  GET  /                        -> web/index.html (ohne Auth, fragt Token ab)
  GET  /api/health              -> {ok} (ohne Auth)
  *alles /api/* sonst*          -> braucht Authorization: Bearer <GF_TOKEN>
  GET  /api/stats
  GET  /api/assets?status=&q=&week=&page=&per_page=
  GET  /api/thumb/<id>          -> image/webp (Thumb als Blob, mit Auth)
  GET  /api/image/<id>          -> Original (mit Auth)
  PATCH /api/assets/<id>        -> {description, tags}
  POST /api/assets/<id>/approve -> Status READY_FOR_RELEASE
  POST /api/assets/<id>/reject  -> Datei nach rejected/, Status REJECTED
  GET  /api/releases            -> Wochen-Ordner mit release.json
  GET  /releases/<pfad>         -> echte Galerie-Dateien (mit Auth)
  POST /api/buzzer              -> startet Job, {job_id}
  GET  /api/job/<id>            -> Fortschritt {step, step_idx, steps, current, total, msg, log, done, error}
  GET  /api/logs?lines=120      -> tail galleryforge.log
"""

import contextlib
import io
import os
import secrets
import shutil
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)  # config_loader nutzt relativen Pfad config/app.yaml

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

from core.config_loader import load_config

config = load_config()
ASSETS_DIR = Path(config["paths"]["assets"])
RELEASES_DIR = Path(config["paths"]["releases"])
DATA_DIR = Path(config["paths"]["data"])
LOGS_DIR = Path(config["paths"]["logs"])
BACKUPS_DIR = DATA_DIR.parent / "backups"
THUMBS_DIR = ASSETS_DIR / "thumbnails"
REJECTED_DIR = ASSETS_DIR / "rejected"
INBOX_DIR = ASSETS_DIR / "inbox"
DB_PATH = DATA_DIR / "galleryforge.db"
BERLIN = ZoneInfo("Europe/Berlin")
PORT = 15001

for d in (THUMBS_DIR, REJECTED_DIR, BACKUPS_DIR, LOGS_DIR, ROOT / "web"):
    d.mkdir(parents=True, exist_ok=True)

# --- Token (.env, nur WireGuard/LAN + Bearer) ---
ENV_FILE = ROOT / ".env"


def get_token() -> str:
    tok = os.environ.get("GF_TOKEN")
    if tok:
        return tok
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("GF_TOKEN="):
                tok = line.split("=", 1)[1].strip().strip('"').strip("'")
                if tok:
                    return tok
    tok = secrets.token_urlsafe(32)
    with open(ENV_FILE, "a") as f:
        f.write(f"\nGF_TOKEN={tok}\n")
    print(f"GF_TOKEN neu erzeugt und in .env gespeichert:\n{tok}\n")
    return tok


TOKEN = get_token()

# --- DB-Migration (database.py kennt neue Spalten nicht) ---
MIGRATIONS = {
    "thumbnail_path": "TEXT",
    "release_id": "TEXT",
    "published_at": "TEXT",
    "description": "TEXT",
    "platform_deviantart": "INTEGER DEFAULT 0",
    "platform_patreon": "INTEGER DEFAULT 0",
    "width": "INTEGER",
    "height": "INTEGER",
    "duration_seconds": "REAL",
    "tags": "TEXT",
}


def ensure_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL,
        filepath TEXT NOT NULL, asset_type TEXT NOT NULL, file_size INTEGER,
        sha256 TEXT, created_at TEXT, status TEXT DEFAULT 'NEW')"""
    )
    cols = {r[1] for r in cur.execute("PRAGMA table_info(assets)").fetchall()}
    for name, ddl in MIGRATIONS.items():
        if name not in cols:
            cur.execute(f"ALTER TABLE assets ADD COLUMN {name} {ddl}")
    conn.commit()
    conn.close()


ensure_db()

app = Flask(__name__)
CORS(app, supports_credentials=False)


def need_auth():
    if request.path == "/" or request.path == "/api/health":
        return None
    if request.path.startswith("/releases/") or request.path.startswith("/api/"):
        auth = request.headers.get("Authorization", "")
        if auth == f"Bearer {TOKEN}":
            return None
        # Token auch als ?token= für direkte Links erlauben (Gallery-Bilder)
        if request.args.get("token") == TOKEN:
            return None
        # Cookie für eingebettete <img>/<a> in Galerie-Seiten (Browser
        # schickt relative Anfragen ohne Header/Query los)
        if request.cookies.get("gf_token") == TOKEN:
            return None
        return jsonify({"error": "unauthorized"}), 401
    return None


@app.before_request
def _auth():
    r = need_auth()
    if r is not None:
        return r


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "app": "GalleryForge", "port": PORT})


@app.get("/")
def index():
    return send_file(ROOT / "web" / "index.html", mimetype="text/html")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/stats")
def stats():
    conn = db()
    rows = conn.execute(
        "SELECT status, COUNT(*) c FROM assets GROUP BY status"
    ).fetchall()
    by_status = {r["status"]: r["c"] for r in rows}
    total = sum(by_status.values())
    try:
        cur = conn.execute(
            "SELECT release_id FROM assets WHERE release_id IS NOT NULL"
            " ORDER BY release_id DESC LIMIT 1"
        ).fetchone()
        current_release = cur["release_id"] if cur else None
        rel_count = conn.execute(
            "SELECT COUNT(DISTINCT release_id) c FROM assets"
            " WHERE release_id IS NOT NULL"
        ).fetchone()["c"]
    except sqlite3.OperationalError:
        current_release, rel_count = None, 0
    conn.close()
    inbox_n = sum(1 for p in INBOX_DIR.iterdir() if p.is_file()) if INBOX_DIR.exists() else 0
    return jsonify(
        {
            "by_status": by_status,
            "total": total,
            "releases": rel_count,
            "current_release": current_release,
            "inbox_files": inbox_n,
        }
    )


def _mtime_week(filepath: str) -> str | None:
    try:
        ts = Path(filepath).stat().st_mtime
    except OSError:
        return None
    dt = datetime.fromtimestamp(ts, tz=BERLIN)
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


@app.get("/api/assets")
def assets():
    status = request.args.get("status", "")
    q = request.args.get("q", "").strip()
    week = request.args.get("week", "").strip()
    try:
        page = max(1, int(request.args.get("page", "1")))
        per = min(100, max(5, int(request.args.get("per_page", "30"))))
    except ValueError:
        page, per = 1, 30
    where, args = [], []
    if status:
        where.append("status = ?")
        args.append(status)
    if week:
        where.append("release_id = ?")
        args.append(week)
    if q:
        where.append("(filename LIKE ? OR description LIKE ? OR tags LIKE ?)")
        args += [f"%{q}%"] * 3
    w = ("WHERE " + " AND ".join(where)) if where else ""
    conn = db()
    total = conn.execute(f"SELECT COUNT(*) c FROM assets {w}", args).fetchone()["c"]
    rows = conn.execute(
        f"SELECT id, filename, filepath, asset_type, status, thumbnail_path,"
        f" release_id, description, tags, created_at FROM assets {w}"
        f" ORDER BY id DESC LIMIT ? OFFSET ?",
        (*args, per, (page - 1) * per),
    ).fetchall()
    conn.close()
    items = []
    for r in rows:
        d = dict(r)
        tp = d.get("thumbnail_path")
        d["has_thumb"] = bool(tp and Path(tp).exists())
        d["week"] = _mtime_week(d["filepath"])
        # Beschreibung/Tags kuerzen erledigt das Frontend (kein Overflow)
        items.append(d)
    return jsonify({"total": total, "page": page, "per_page": per, "items": items})


def _send_path(path_str: str, fallback_mime: str):
    p = Path(path_str or "")
    if not p.exists() or not p.is_file():
        return jsonify({"error": "missing file"}), 404
    return send_file(p)


@app.get("/api/thumb/<int:asset_id>")
def thumb(asset_id):
    conn = db()
    r = conn.execute(
        "SELECT thumbnail_path FROM assets WHERE id = ?", (asset_id,)
    ).fetchone()
    conn.close()
    if not r:
        return jsonify({"error": "not found"}), 404
    return _send_path(r["thumbnail_path"], "image/webp")


@app.get("/api/image/<int:asset_id>")
def image(asset_id):
    conn = db()
    r = conn.execute("SELECT filepath FROM assets WHERE id = ?", (asset_id,)).fetchone()
    conn.close()
    if not r:
        return jsonify({"error": "not found"}), 404
    return _send_path(r["filepath"], "application/octet-stream")


@app.patch("/api/assets/<int:asset_id>")
def edit_asset(asset_id):
    data = request.get_json(force=True, silent=True) or {}
    desc = data.get("description")
    tags = data.get("tags")
    if isinstance(tags, list):
        tags = ", ".join(t.strip() for t in tags if t.strip())
    conn = db()
    cur = conn.execute("SELECT id FROM assets WHERE id = ?", (asset_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({"error": "not found"}), 404
    if desc is not None:
        conn.execute("UPDATE assets SET description = ? WHERE id = ?", (desc, asset_id))
    if tags is not None:
        conn.execute("UPDATE assets SET tags = ? WHERE id = ?", (tags, asset_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.post("/api/assets/<int:asset_id>/approve")
def approve(asset_id):
    conn = db()
    cur = conn.execute(
        "UPDATE assets SET status = 'READY_FOR_RELEASE' WHERE id = ?"
        " AND status != 'REJECTED'",
        (asset_id,),
    )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return jsonify({"ok": ok})


@app.post("/api/assets/<int:asset_id>/reject")
def reject(asset_id):
    conn = db()
    r = conn.execute(
        "SELECT filepath FROM assets WHERE id = ?", (asset_id,)
    ).fetchone()
    if not r:
        conn.close()
        return jsonify({"error": "not found"}), 404
    src = Path(r["filepath"])
    new_path = str(src)
    try:
        if src.exists():
            dest = REJECTED_DIR / src.name
            i = 1
            while dest.exists():
                dest = REJECTED_DIR / f"{src.stem}_{i}{src.suffix}"
                i += 1
            shutil.move(str(src), str(dest))
            new_path = str(dest)
    except OSError as e:
        conn.close()
        return jsonify({"error": str(e)}), 500
    conn.execute(
        "UPDATE assets SET status = 'REJECTED', filepath = ? WHERE id = ?",
        (new_path, asset_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.get("/api/releases")
def releases():
    import re as _re

    out = []
    if RELEASES_DIR.exists():
        for sub in sorted(RELEASES_DIR.iterdir(), reverse=True):
            if not sub.is_dir():
                continue
            if not _re.match(r"^\d{4}-W\d{2}$", sub.name):
                continue
            rj = sub / "release.json"
            info = {}
            if rj.exists():
                try:
                    import json as _j

                    info = _j.loads(rj.read_text(encoding="utf-8"))
                except Exception:
                    info = {}
            out.append(
                {
                    "id": sub.name,
                    "assets": info.get("asset_count", len(info.get("assets", []))),
                    "has_index": (sub / "index.html").exists(),
                }
            )
    return jsonify({"releases": out})


@app.get("/releases/<path:subpath>")
def serve_release(subpath):
    return send_from_directory(RELEASES_DIR, subpath)


@app.get("/api/logs")
def logs():
    try:
        n = min(500, max(20, int(request.args.get("lines", "120"))))
    except ValueError:
        n = 120
    lf = LOGS_DIR / "galleryforge.log"
    if not lf.exists():
        return jsonify({"lines": []})
    with open(lf, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()[-n:]
    return jsonify({"lines": [ln.rstrip("\n") for ln in lines]})


# --- Buzzer: 1 Knopf, alles nacheinander, mit Fortschritt ---
jobs: dict[str, dict] = {}
jlock = threading.Lock()


def _job_update(jid, **kw):
    with jlock:
        j = jobs.get(jid)
        if j is None:
            return
        j.update(kw)
        j["updated_at"] = time.time()
        if "msg" in kw:
            j["log"].append(f"[{kw.get('step', j.get('step', ''))}] {kw['msg']}")
            j["log"] = j["log"][-300:]


def _call_quiet(jid, fn, *a, **k):
    """Core-Funktionen printen viel (Scanner/Builder). stdout ist im
    Hintergrund-Server ggf. eine geschlossene Pipe -> BrokenPipeError.
    Darum alles abfangen und nur die letzten Zeilen ins Job-Log legen."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            return fn(*a, **k)
    finally:
        txt = buf.getvalue().strip()
        if txt:
            for line in txt.splitlines()[-6:]:
                _job_update(jid, msg="log: " + line[:160])


def _run_buzzer(jid):
    from core.asset_registry import get_assets_by_status

    steps = ["scan", "beschreiben", "thumbs", "release", "build"]
    try:
        # 1) Scan
        _job_update(jid, step="scan", step_idx=1, steps=steps, current=0, total=1,
                     msg="Scanne Inbox ...")
        from core import scanner as _scanner

        before = len(get_assets_by_status("NEW"))
        _call_quiet(jid, _scanner.scan_inbox)
        after = len(get_assets_by_status("NEW"))
        _job_update(jid, current=1, total=1, msg=f"Scan fertig: {max(0, after - before)} neu (NEW: {after})")

        # 2) Beschreiben (pro Asset, kann Minuten dauern)
        from core import describer as _desc

        todo = []
        for st in ("NEW", "THUMBNAILED"):
            todo.extend(get_assets_by_status(st))
        ok, fail = 0, 0
        for i, a in enumerate(todo, 1):
            aid, fn, fp, at, _st = a[0], a[1], a[2], a[3], a[4]
            _job_update(jid, step="beschreiben", step_idx=2, current=i, total=max(1, len(todo)),
                         msg=f"Beschreibe [{aid}] {fn} ({i}/{len(todo)})")
            try:
                res = _call_quiet(jid, _desc.describe_asset, fp, fn, at)
            except Exception as e:  # Ollama/LM-Studio weg? weiter, nicht abbrechen
                res = None
                _job_update(jid, msg=f"Fehler bei [{aid}]: {type(e).__name__}")
            if res:
                _desc.save_result(aid, res[0], res[1])
                ok += 1
            else:
                fail += 1
        _job_update(jid, msg=f"Beschreiben fertig: {ok} ok, {fail} übersprungen")

        # 3) Thumbs (ohne Video-Finisher, Status DESCRIBED bleibt erhalten)
        from core import thumbnailer as _th

        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT id, filename, filepath, asset_type, status, description,"
            " thumbnail_path FROM assets WHERE status IN ('NEW','DESCRIBED')"
        ).fetchall()
        done_t, fail_t = 0, 0
        for i, (aid, fn, fp, at, st, desc, tp) in enumerate(rows, 1):
            _job_update(jid, step="thumbs", step_idx=3, current=i, total=max(1, len(rows)),
                         msg=f"Thumb {i}/{len(rows)}: {fn}")
            src = Path(fp)
            if not src.exists():
                fail_t += 1
                continue
            if tp and Path(tp).exists():
                done_t += 1
                if st == "NEW":  # Thumb da, aber Status alt -> heilen
                    conn.execute("UPDATE assets SET status='THUMBNAILED' WHERE id=?", (aid,))
                    conn.commit()
                continue
            target = THUMBS_DIR / f"{src.stem}.webp"
            try:
                if at == "video":
                    _th.create_video_thumbnail(src, target)
                else:
                    _th.create_thumbnail(src, target)
            except Exception as e:
                fail_t += 1
                _job_update(jid, msg=f"Thumb-Fehler {fn}: {type(e).__name__}")
                continue
            keep = "DESCRIBED" if (st == "DESCRIBED" or desc) else "THUMBNAILED"
            conn.execute(
                "UPDATE assets SET thumbnail_path=?, status=? WHERE id=?",
                (str(target), keep, aid),
            )
            conn.commit()
            done_t += 1
        conn.close()
        _job_update(jid, msg=f"Thumbs fertig: {done_t} ok, {fail_t} fehlen")

        # 4) Release nach mtime-Woche (Statusfix: DESCRIBED+THUMBNAILED+READY ohne release)
        _job_update(jid, step="release", step_idx=4, current=0, total=1,
                     msg="Ordne Wochen zu (mtime, Europe/Berlin) ...")
        try:
            BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(DB_PATH, BACKUPS_DIR / f"galleryforge-{stamp}.db")
            _job_update(jid, msg=f"DB-Backup: galleryforge-{stamp}.db")
        except Exception as e:
            _job_update(jid, msg=f"Backup-Warnung: {e}")
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT id, filepath FROM assets WHERE status IN"
            " ('DESCRIBED','THUMBNAILED','READY_FOR_RELEASE')"
            " AND (release_id IS NULL OR release_id='')"
            " AND status != 'REJECTED'"
        ).fetchall()
        weeks: dict[str, int] = {}
        for aid, fp in rows:
            wk = _mtime_week(fp)
            if not wk:
                continue
            conn.execute(
                "UPDATE assets SET release_id=?, status='READY_FOR_RELEASE' WHERE id=?",
                (wk, aid),
            )
            weeks[wk] = weeks.get(wk, 0) + 1
        conn.commit()
        conn.close()
        _job_update(jid, current=1, total=1,
                     msg=f"Release zugeordnet: {sum(weeks.values())} Assets -> {weeks or 'nichts neu'}")

        # 5) Build je Woche + Stats
        from core import gallery_builder as _gb

        if weeks:
            for i, wk in enumerate(sorted(weeks), 1):
                _job_update(jid, step="build", step_idx=5, current=i, total=len(weeks),
                             msg=f"Baue Galerie {wk} ({i}/{len(weeks)}) ...")
                try:
                    _call_quiet(jid, _gb.build_gallery, wk)
                except Exception as e:
                    _job_update(jid, msg=f"Build-Fehler {wk}: {type(e).__name__}: {e}")
        else:
            # trotzdem aktuelle Woche bauen falls READY vorhanden (z.B. nur Freigaben)
            _job_update(jid, step="build", step_idx=5, current=1, total=1,
                         msg="Baue aktuelle Woche ...")
            try:
                conn = sqlite3.connect(DB_PATH)
                r = conn.execute(
                    "SELECT release_id FROM assets WHERE release_id IS NOT NULL"
                    " ORDER BY release_id DESC LIMIT 1"
                ).fetchone()
                conn.close()
                if r:
                    _call_quiet(jid, _gb.build_gallery, r[0])
            except Exception as e:
                _job_update(jid, msg=f"Build-Fehler: {e}")
        _job_update(jid, done=True, current=1, total=1, msg="Fertig.")
    except Exception as e:
        _job_update(jid, done=True, error=f"{type(e).__name__}: {e}",
                     msg=f"ABBRUCH: {e}")


@app.get("/api/missing")
def missing():
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM assets WHERE status = 'READY_FOR_RELEASE'"
        " AND (description IS NULL OR description = '')"
    ).fetchone()["c"]
    conn.close()
    return jsonify({"missing": n})


def _run_backfill(jid):
    from core import describer as _desc

    steps = ["nachholen"]
    try:
        todo = _desc.get_missing_descriptions()
        ok, fail = 0, 0
        for i, a in enumerate(todo, 1):
            aid, fn, fp, at = a[0], a[1], a[2], a[3]
            _job_update(jid, step="nachholen", step_idx=1, steps=steps,
                         current=i, total=max(1, len(todo)),
                         msg=f"Hole nach [{aid}] {fn} ({i}/{len(todo)})")
            try:
                res = _call_quiet(jid, _desc.describe_asset, fp, fn, at)
            except Exception as e:
                res = None
                _job_update(jid, msg=f"Fehler bei [{aid}]: {type(e).__name__}")
            if res:
                _desc.save_backfill(aid, res[0], res[1])
                ok += 1
            else:
                fail += 1
        _job_update(jid, done=True, current=1, total=1,
                     msg=f"Nachgeholt: {ok} ok, {fail} übersprungen.")
    except Exception as e:
        _job_update(jid, done=True, error=f"{type(e).__name__}: {e}",
                     msg=f"ABBRUCH: {e}")


@app.post("/api/backfill")
def backfill():
    jid = uuid.uuid4().hex[:12]
    with jlock:
        jobs[jid] = {"step": "start", "step_idx": 0,
                      "steps": ["nachholen"],
                      "current": 0, "total": 1, "msg": "Start ...",
                      "log": [], "done": False, "error": None,
                      "started_at": time.time()}
    t = threading.Thread(target=_run_backfill, args=(jid,), daemon=True)
    t.start()
    return jsonify({"job_id": jid})


@app.post("/api/buzzer")
def buzzer():
    jid = uuid.uuid4().hex[:12]
    with jlock:
        jobs[jid] = {"step": "start", "step_idx": 0,
                      "steps": ["scan", "beschreiben", "thumbs", "release", "build"],
                      "current": 0, "total": 1, "msg": "Start ...",
                      "log": [], "done": False, "error": None,
                      "started_at": time.time()}
    t = threading.Thread(target=_run_buzzer, args=(jid,), daemon=True)
    t.start()
    return jsonify({"job_id": jid})


def _run_rebuild(jid):
    from core import gallery_builder as _gb

    steps = ["rebuild"]
    try:
        conn = sqlite3.connect(DB_PATH)
        weeks = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT release_id FROM assets"
                " WHERE release_id IS NOT NULL AND release_id != ''"
                " ORDER BY release_id"
            ).fetchall()
        ]
        conn.close()
        ok, fail = 0, 0
        for i, wk in enumerate(weeks, 1):
            _job_update(jid, step="rebuild", step_idx=1, steps=steps,
                         current=i, total=max(1, len(weeks)),
                         msg=f"Baue {wk} neu ({i}/{len(weeks)}) ...")
            try:
                _call_quiet(jid, _gb.build_gallery, wk)
                ok += 1
            except Exception as e:
                fail += 1
                _job_update(jid, msg=f"Build-Fehler {wk}: {type(e).__name__}: {e}")
        _job_update(jid, done=True, current=1, total=1,
                     msg=f"Rebuild fertig: {ok} ok, {fail} Fehler.")
    except Exception as e:
        _job_update(jid, done=True, error=f"{type(e).__name__}: {e}",
                     msg=f"ABBRUCH: {e}")


@app.post("/api/rebuild")
def rebuild():
    jid = uuid.uuid4().hex[:12]
    with jlock:
        jobs[jid] = {"step": "start", "step_idx": 0,
                      "steps": ["rebuild"],
                      "current": 0, "total": 1, "msg": "Start ...",
                      "log": [], "done": False, "error": None,
                      "started_at": time.time()}
    t = threading.Thread(target=_run_rebuild, args=(jid,), daemon=True)
    t.start()
    return jsonify({"job_id": jid})


@app.get("/api/jobs")
def jobs_list():
    with jlock:
        return jsonify(
            {
                jid: {
                    "step": j.get("step"),
                    "step_idx": j.get("step_idx"),
                    "current": j.get("current"),
                    "total": j.get("total"),
                    "msg": (j.get("msg") or "")[:200],
                    "log_tail": j.get("log", [])[-15:],
                    "done": j.get("done"),
                    "error": j.get("error"),
                    "updated_at": j.get("updated_at"),
                }
                for jid, j in jobs.items()
            }
        )


@app.get("/api/job/<jid>")
def job(jid):
    with jlock:
        j = jobs.get(jid)
        if not j:
            return jsonify({"error": "unknown job"}), 404
        return jsonify({"job_id": jid, **j})


if __name__ == "__main__":
    try:
        print(f"GalleryForge Web: http://0.0.0.0:{PORT}/  (Token in .env: GF_TOKEN)")
    except BrokenPipeError:
        pass  # Hintergrundstart ohne Konsole
    app.run(host="0.0.0.0", port=PORT, threaded=True)
