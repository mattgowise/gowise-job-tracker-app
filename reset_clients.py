import sqlite3

# Connect to your local database
conn = sqlite3.connect('gowise.db')
cursor = conn.cursor()

# 1. Wipe the customers table completely clean
cursor.execute('DELETE FROM customers')

# 2. Add the three test clients back in
clients = [
    ('Norwich Arts Centre', 'Sarah Smith', 'sarah@example.com'),
    ('The Folklore Box', 'Matt Willis', 'hello@thefolklorebox.com'),
    ('Brundall Parish Council', 'John Doe', 'john@example.com')
]

cursor.executemany('''
    INSERT INTO customers (company_name, contact_name, email) 
    VALUES (?, ?, ?)
''', clients)

# 3. Save the changes
conn.commit()
conn.close()

print("Success! The table was wiped and exactly 3 clients were added.")