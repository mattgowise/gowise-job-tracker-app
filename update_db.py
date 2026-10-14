import sqlite3

conn = sqlite3.connect('gowise.db')
cursor = conn.cursor()

# The new columns we need to add to the existing table
new_columns = [
    "primary_job_title TEXT",
    "primary_phone TEXT",
    "secondary_contact_name TEXT",
    "secondary_job_title TEXT",
    "secondary_email TEXT",
    "secondary_phone TEXT",
    "notes TEXT"
]

for column in new_columns:
    try:
        cursor.execute(f"ALTER TABLE customers ADD COLUMN {column}")
        print(f"Added column: {column}")
    except sqlite3.OperationalError:
        # If the column already exists, it will throw an error, which we can safely ignore
        print(f"Column already exists: {column}")

conn.commit()
conn.close()
print("Database upgrade complete!")