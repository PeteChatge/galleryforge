#!/usr/bin/env python3
"""
GalleryForge - DeviantArt Publish (Sta.sh API)

Zweistufig, bewusst getrennt zum sicheren Testen:
  1. submit   -> Datei + Titel + Beschreibung + Tags als PRIVATEN Draft in
                 Sta.sh hochladen. Geht noch NICHT live.
  2. publish  -> Einen vorhandenen Draft (itemid) tatsächlich veröffentlichen.

Speichern als: core/da_publish.py

Nutzung:
    python3 -m core.da_publish submit <asset_id> [stack_name]  # Draft, optional in Monats-Ordner
    python3 -m core.da_publish publish <asset_id>               # gespeicherten Draft veroeffentlichen
    python3 -m core.da_publish list                             # offene Assets zeigen
    python3 -m core.da_publish folders                          # Sta.sh-Ordner + stackid auflisten
    python3 -m core.da_publish folder-remove <stackid>           # Ordner entfernen (nach 3-4 Monaten)
"""

import json
import sys
from pathlib import Path

import requests

from core.database import get_connection
from core.da_auth import get_valid_access_token

STASH_SUBMIT_URL = "https://www.deviantart.com/api/v1/oauth2/stash/submit"
STASH_PUBLISH_URL = "https://www.deviantart.com/api/v1/oauth2/stash/publish"


def get_asset(asset_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, filename, filepath, description, tags, platform_deviantart "
        "FROM assets WHERE id = ?",
        (asset_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def get_unpublished_assets():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, filename, description, tags FROM assets "
        "WHERE status = 'READY_FOR_RELEASE' "
        "AND (platform_deviantart IS NULL OR platform_deviantart = '')"
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def stash_submit(filepath: str, title: str, description: str, tags: list[str],
                  is_mature: bool = True, stack: str | None = None) -> dict | None:
    """Lädt eine Datei als privaten Draft zu Sta.sh hoch.
    Gibt {itemid, stack, stackid} zurück."""
    token = get_valid_access_token()
    data = {
        "access_token": token,
        "title": title,
        "artist_comments": description,
        "is_mature": "1" if is_mature else "0",
        "is_ai_generated": "1",
    }
    if tags:
        data["tags[]"] = tags
    if stack:
        data["stack"] = stack  # Name des Monats-Ordners, z.B. "2026-06"

    try:
        with open(filepath, "rb") as f:
            files = {"file": (Path(filepath).name, f)}
            response = requests.post(
                STASH_SUBMIT_URL, data=data, files=files, timeout=180
            )
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.RequestException as e:
        print(f"  FEHLER: {type(e).__name__}: {e}")
        return None

    if result.get("status") != "success":
        print(f"  FEHLER von DeviantArt: {result}")
        return None

    return result


def stash_publish(itemid: int, is_mature: bool = True,
                   allow_comments: bool = True, feature: bool = False) -> dict | None:
    """Veröffentlicht einen Sta.sh-Draft. Gibt {url, deviationid} zurück."""
    token = get_valid_access_token()
    data = {
        "access_token": token,
        "itemid": itemid,
        "is_mature": "1" if is_mature else "0",
        "allow_comments": "1" if allow_comments else "0",
        "feature": "1" if feature else "0",
    }

    try:
        response = requests.post(STASH_PUBLISH_URL, data=data, timeout=60)
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.RequestException as e:
        print(f"  FEHLER: {type(e).__name__}: {e}")
        return None

    if result.get("status") != "success":
        print(f"  FEHLER von DeviantArt: {result}")
        return None

    return result


def stash_folders() -> list[dict] | None:
    """Listet alle Sta.sh-Ordner (Stacks)."""
    token = get_valid_access_token()
    try:
        response = requests.post(
            "https://www.deviantart.com/api/v1/oauth2/stash/folders",
            data={"access_token": token},
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.RequestException as e:
        print(f"  FEHLER: {type(e).__name__}: {e}")
        return None

    if result.get("status") != "success":
        print(f"  FEHLER von DeviantArt: {result}")
        return None
    return result.get("results", [])


def stash_folder_remove(stackid: int) -> bool:
    """Entfernt einen Sta.sh-Ordner (Stack)."""
    token = get_valid_access_token()
    try:
        response = requests.post(
            f"https://www.deviantart.com/api/v1/oauth2/stash/folders/remove/{stackid}",
            data={"access_token": token},
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.RequestException as e:
        print(f"  FEHLER: {type(e).__name__}: {e}")
        return False

    if result.get("status") != "success":
        print(f"  FEHLER von DeviantArt: {result}")
        return False
    return True


def save_draft_info(asset_id: int, itemid: int, stack: str | None = None, stackid: int | None = None):
    conn = get_connection()
    conn.execute(
        "UPDATE assets SET platform_deviantart = ? WHERE id = ?",
        (json.dumps({"itemid": itemid, "stack": stack, "stackid": stackid, "status": "draft"}), asset_id),
    )
    conn.commit()
    conn.close()


def get_stored_itemid(asset_id: int) -> int | None:
    row = get_asset(asset_id)
    if not row or not row[5]:
        return None
    try:
        info = json.loads(row[5])
        return info.get("itemid")
    except (json.JSONDecodeError, AttributeError):
        return None


def save_platform_info(asset_id: int, deviationid: str, url: str):
    conn = get_connection()
    conn.execute(
        "UPDATE assets SET platform_deviantart = ?, published_at = CURRENT_TIMESTAMP "
        "WHERE id = ?",
        (json.dumps({"deviationid": deviationid, "url": url}), asset_id),
    )
    conn.commit()
    conn.close()


def cmd_submit(asset_id: int, stack: str | None = None):
    row = get_asset(asset_id)
    if not row:
        print(f"Asset {asset_id} nicht gefunden.")
        return
    _, filename, filepath, description, tags_raw, _ = row
    tags = [t.strip() for t in (tags_raw or "").split(",") if t.strip()]
    title = Path(filename).stem

    stack_info = f" -> Ordner '{stack}'" if stack else ""
    print(f"Submitte [{asset_id}] {filename} als Draft{stack_info}...")
    result = stash_submit(filepath, title, description or "", tags, stack=stack)
    if result:
        itemid = result["itemid"]
        save_draft_info(asset_id, itemid, result.get("stack"), result.get("stackid"))
        print(f"\nDraft erstellt: itemid={itemid}, stack='{result.get('stack')}' "
              f"(stackid={result.get('stackid')}) - in DB gespeichert")
        print("Bitte JETZT in deinem Sta.sh-Account pruefen (Tags, Beschreibung, AI-Label).")
        print(f"Danach veroeffentlichen mit:\n  python3 -m core.da_publish publish {asset_id}")
    else:
        print("Fehlgeschlagen.")


def cmd_publish(asset_id: int, itemid: int | None = None):
    if itemid is None:
        itemid = get_stored_itemid(asset_id)
        if itemid is None:
            print(f"Keine gespeicherte itemid fuer Asset {asset_id} gefunden. "
                  f"Erst 'submit {asset_id}' ausfuehren, oder itemid manuell angeben:")
            print(f"  python3 -m core.da_publish publish {asset_id} <itemid>")
            return

    print(f"Veroeffentliche itemid={itemid} fuer Asset [{asset_id}]...")
    result = stash_publish(itemid)
    if result:
        save_platform_info(asset_id, result["deviationid"], result["url"])
        print(f"\nVeroeffentlicht: {result['url']}")
    else:
        print("Fehlgeschlagen.")


def cmd_folders():
    folders = stash_folders()
    if not folders:
        print("Keine Ordner gefunden (oder Fehler).")
        return
    print(f"{len(folders)} Sta.sh-Ordner:\n")
    for f in folders:
        print(f"  stackid={f.get('folderid')}  '{f.get('title')}'  ({f.get('size', '?')} Items)")


def cmd_folder_remove(stackid: int):
    print(f"Entferne Ordner stackid={stackid}...")
    if stash_folder_remove(stackid):
        print("Entfernt.")
    else:
        print("Fehlgeschlagen.")


def cmd_list():
    rows = get_unpublished_assets()
    if not rows:
        print("Keine offenen (READY_FOR_RELEASE, noch nicht auf DA) Assets.")
        return
    print(f"{len(rows)} Assets bereit für DeviantArt:\n")
    for asset_id, filename, description, tags in rows:
        print(f"[{asset_id}] {filename}")
        print(f"  Tags: {tags or '(keine)'}")
        print()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "submit" and len(sys.argv) == 3:
        cmd_submit(int(sys.argv[2]))
    elif len(sys.argv) >= 2 and sys.argv[1] == "submit" and len(sys.argv) == 4:
        cmd_submit(int(sys.argv[2]), sys.argv[3])
    elif len(sys.argv) >= 2 and sys.argv[1] == "publish" and len(sys.argv) == 3:
        cmd_publish(int(sys.argv[2]))
    elif len(sys.argv) >= 2 and sys.argv[1] == "publish" and len(sys.argv) == 4:
        cmd_publish(int(sys.argv[2]), int(sys.argv[3]))
    elif len(sys.argv) == 2 and sys.argv[1] == "list":
        cmd_list()
    elif len(sys.argv) == 2 and sys.argv[1] == "folders":
        cmd_folders()
    elif len(sys.argv) == 3 and sys.argv[1] == "folder-remove":
        cmd_folder_remove(int(sys.argv[2]))
    else:
        print(__doc__)
