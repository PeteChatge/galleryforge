import sqlite3
from pathlib import Path

from core.config_loader import load_config

config = load_config()

DB_PATH = Path(config["paths"]["data"]) / "galleryforge.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def initialize_database():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        filepath TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        file_size INTEGER,
        sha256 TEXT,
        created_at TEXT,
        status TEXT DEFAULT 'NEW'
    )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    initialize_database()
    print(f"Database initialized: {DB_PATH}")
