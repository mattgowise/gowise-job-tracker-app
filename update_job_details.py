import sqlite3

conn = sqlite3.connect('gowise.db')
cursor = conn.cursor()

new_columns = [
    "date_received TEXT",
    "quantity TEXT",
    "ink TEXT",
    "finishing TEXT",
    "price TEXT"
]

for column in new_columns:
    try:
        cursor.execute(f"ALTER TABLE jobs ADD COLUMN {column}")
        print(f"Added column: {column}")
    except sqlite3.OperationalError:
        print(f"Column already exists: {column}")

conn.commit()
conn.close()
print("Job details schema updated successfully!")