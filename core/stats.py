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

    for status, count in rows:
        print(f"{status:20} {count}")
        total += count

    print()
    print(f"TOTAL ASSETS        {total}")

    conn.close()


if __name__ == "__main__":
    show_stats()
