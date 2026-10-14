import sqlite3

# Connect to your local database
conn = sqlite3.connect('gowise.db')
cursor = conn.cursor()

# A list of dummy clients to test the system
clients = [
    ('Norwich Arts Centre', 'Sarah Smith', 'sarah@example.com'),
    ('The Folklore Box', 'Matt Willis', 'hello@thefolklorebox.com'),
    ('Brundall Parish Council', 'John Doe', 'john@example.com')
]

# Insert them into the customers table
cursor.executemany('''
    INSERT INTO customers (company_name, contact_name, email) 
    VALUES (?, ?, ?)
''', clients)

conn.commit()
conn.close()

print("Test clients added successfully!")