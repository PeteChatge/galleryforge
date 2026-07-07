from datetime import datetime

from core.database import get_connection


def create_release_id():

    now = datetime.now()

    year = now.strftime("%Y")
    week = now.strftime("%V")

    return f"{year}-W{week}"


def assign_assets_to_release():

    release_id = create_release_id()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE assets
        SET
            release_id = ?,
            status = 'READY_FOR_RELEASE'
        WHERE status = 'THUMBNAILED'
        """,
        (release_id,)
    )

    affected = cursor.rowcount

    conn.commit()
    conn.close()

    return affected, release_id

def get_release_assets(release_id):

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            filename,
            filepath,
            thumbnail_path,
            description,
            tags
        FROM assets
        WHERE release_id = ?
        ORDER BY id
        """,
        (release_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


if __name__ == "__main__":

    affected, release_id = (
        assign_assets_to_release()
    )

    print()

    print(
        f"Assigned {affected} assets "
        f"to release {release_id}"
    )
