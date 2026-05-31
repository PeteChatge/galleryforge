from pathlib import Path
from datetime import datetime, UTC
import hashlib

from core.database import get_connection


def calculate_sha256(file_path):

    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def asset_exists(sha256):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM assets WHERE sha256 = ?",
        (sha256,)
    )

    result = cursor.fetchone()

    conn.close()

    return result is not None


def register_asset(file_path, asset_type):

    file_path = Path(file_path)

    conn = get_connection()
    cursor = conn.cursor()

    sha256 = calculate_sha256(file_path)

    if asset_exists(sha256):
        print(f"Asset already exists: {file_path.name}")
        conn.close()
        return False

    cursor.execute(
        """
        INSERT INTO assets (
            filename,
            filepath,
            asset_type,
            file_size,
            sha256,
            created_at,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            file_path.name,
            str(file_path),
            asset_type,
            file_path.stat().st_size,
            sha256,
            datetime.now(UTC).isoformat(),
            "NEW"
        )
    )

    conn.commit()
    conn.close()

    return True


def get_assets_by_status(status):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            filename,
            filepath,
            asset_type,
            status
        FROM assets
        WHERE status = ?
        ORDER BY id
        """,
        (status,)
    )

    rows = cursor.fetchall()

    conn.close()

    return rows


def get_new_assets():
    return get_assets_by_status("NEW")


def update_thumbnail(asset_id, thumbnail_path):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE assets
        SET
            thumbnail_path = ?,
            status = 'THUMBNAILED'
        WHERE id = ?
        """,
        (thumbnail_path, asset_id)
    )

    conn.commit()
    conn.close()


def update_asset_status(asset_id, status):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE assets
        SET status = ?
        WHERE id = ?
        """,
        (status, asset_id)
    )

    conn.commit()
    conn.close()

if __name__ == "__main__":

    print("\nNEW assets:\n")

    for asset in get_new_assets():
        print(asset)
