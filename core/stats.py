from core.database import get_connection


def show_stats():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT status, COUNT(*)
        FROM assets
        GROUP BY status
        """
    )

    rows = cursor.fetchall()

    print()
    print("GalleryForge Statistics")
    print("=======================")
    print()

    total = 0
    
    cursor.execute(
        """
        SELECT release_id
        FROM assets
        WHERE release_id IS NOT NULL
        ORDER BY release_id DESC
        LIMIT 1
        """
    )
    
    row = cursor.fetchone()
    
    current_release = (
        row[0]
        if row
        else "None"
    )

    cursor.execute(
        """
        SELECT COUNT(DISTINCT release_id)
        FROM assets
        WHERE release_id IS NOT NULL
        """
    )
    
    release_count = cursor.fetchone()[0]

    for status, count in rows:
        print(f"{status:20} {count}")
        total += count

    print()
    print(f"TOTAL ASSETS        {total}")

    print()
    print(f"TOTAL RELEASES     {release_count}")
    print(f"CURRENT RELEASE    {current_release}")

    conn.close()


if __name__ == "__main__":
    show_stats()
