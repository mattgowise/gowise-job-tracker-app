
import sqlite3

conn = sqlite3.connect('gowise.db')
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE jobs ADD COLUMN delivery_date TEXT")
    conn.commit()
    print("Delivery date column added successfully!")
except sqlite3.OperationalError:
    print("Column already exists.")
finally:
    conn.close()