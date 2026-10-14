import sqlite3

# This will create a file called gowise.db in your folder
conn = sqlite3.connect('gowise.db')
cursor = conn.cursor()

# Create Customers Table
cursor.execute('''
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    contact_name TEXT,
    email TEXT
)
''')

# Create Jobs Table (with paper stock and size)
cursor.execute('''
CREATE TABLE IF NOT EXISTS jobs (
    job_number TEXT PRIMARY KEY,
    customer_id INTEGER,
    title TEXT NOT NULL,
    finished_size TEXT,
    paper_stock TEXT,
    current_stage TEXT DEFAULT 'booked in',
    FOREIGN KEY(customer_id) REFERENCES customers(id)
)
''')

# Create Status Logs Table
cursor.execute('''
CREATE TABLE IF NOT EXISTS status_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_number TEXT,
    stage TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(job_number) REFERENCES jobs(job_number)
)
''')

conn.commit()
conn.close()
print("Database initialized successfully!")