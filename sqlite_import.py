import sqlite3

conn = sqlite3.connect("galleryforge.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE assets (
    id INTEGER PRIMARY KEY,
    filename TEXT,
    filepath TEXT
)
""")

conn.commit()
conn.close()
