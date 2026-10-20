import json
import csv
import io
from flask import Response
import os
import multiprocessing
from threading import Timer
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, jsonify
from datetime import datetime, date

app = Flask(__name__, template_folder='templates')

# Paste your full Supabase URI string here
SUPABASE_URI = "postgresql://postgres.lhxpogmftjcwpizztkfi:eALhNDE7ZFK8ewJW@aws-0-eu-north-1.pooler.supabase.com:6543/postgres"

def get_db_connection():
    conn = psycopg2.connect(SUPABASE_URI)
    # Autocommit removes the need to manually call conn.commit() after every change
    conn.autocommit = True 
    return conn

# --- Route 1: The Main Dashboard ---
@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor) 
    
    # 1. Fetch board data & customers (IGNORE paid and bible stages)
    cursor.execute('''
        SELECT jobs.*, customers.company_name, customers.email 
        FROM jobs 
        LEFT JOIN customers ON jobs.customer_id = customers.id
        WHERE jobs.current_stage NOT IN ('paid', 'bible')
    ''')
    jobs = cursor.fetchall()
    
    # Added 'artworking' to the stages array below
    stages = ['booked in', 'artworking', 'on proof', 'amends', 'approved', 'sent to print', 'printed', 'invoiced', 'paid']
    board_data = {stage: [] for stage in stages}
    
    for job in jobs:
        stage = job['current_stage']
        
        if stage:
            stage = stage.lower()
            
        if stage in board_data:
            # Urgency check logic
            urgency = ""
            
            if job['delivery_date'] and str(job['delivery_date']).strip() != '':
                try:
                    due_date = date.fromisoformat(str(job['delivery_date']))
                    today = date.today()
                    delta = (due_date - today).days
                    if delta < 0:
                        urgency = "overdue"
                    elif delta <= 2:
                        urgency = "warning"
                except ValueError:
                    pass
            
            job_dict = dict(job)
            job_dict['urgency'] = urgency
            board_data[stage].append(job_dict)

    cursor.execute('SELECT * FROM customers ORDER BY company_name ASC')
    customers = cursor.fetchall()

    # --- Robust Analytics Calculations ---
    today_str = date.today().isoformat()
    
    # Total Active Jobs
    cursor.execute("SELECT COUNT(*) AS total FROM jobs WHERE current_stage NOT IN ('paid', 'bible')")
    total_active = cursor.fetchone()['total']

    # Overdue Jobs
    cursor.execute("SELECT COUNT(*) AS total FROM jobs WHERE current_stage NOT IN ('paid', 'bible') AND delivery_date IS NOT NULL AND delivery_date != '' AND delivery_date < %s", (today_str,))
    jobs_overdue = cursor.fetchone()['total']

    # Expected Revenue & Pipeline Totals
    cursor.execute("SELECT price, current_stage FROM jobs WHERE current_stage NOT IN ('paid', 'bible')")
    all_active_jobs = cursor.fetchall()
    
    total_pipeline_value = 0.0
    expected_revenue = 0.0
    
    for row in all_active_jobs:
        price_val = row['price']
        stage = row['current_stage'].lower() if row['current_stage'] else ''
        
        if price_val:
            try:
                clean_price = float(str(price_val).replace('£', '').replace(',', '').strip())
                total_pipeline_value += clean_price
                if stage == 'invoiced':
                    expected_revenue += clean_price
            except ValueError:
                pass
                
    uninvoiced_revenue = total_pipeline_value - expected_revenue

    cursor.close()
    conn.close()

    return render_template('index.html', 
                           stages=stages, 
                           board_data=board_data, 
                           customers=customers,
                           total_active=total_active,
                           jobs_overdue=jobs_overdue,
                           total_pipeline_value=total_pipeline_value,
                           uninvoiced_revenue=uninvoiced_revenue,
                           expected_revenue=expected_revenue)

# --- Route 2: Update Stage (Drag and Drop) ---
@app.route('/update_stage', methods=['POST'])
def update_stage():
    data = request.get_json()
    job_number = data.get('job_number')
    new_stage = data.get('stage')

    if not job_number or not new_stage:
        return jsonify({'success': False, 'error': 'Missing data'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            'UPDATE jobs SET current_stage = %s WHERE job_number = %s',
            (new_stage, job_number)
        )
        cursor.execute(
            'INSERT INTO status_logs (job_number, stage) VALUES (%s, %s)',
            (job_number, new_stage)
        )
        success = True
    except Exception as e:
        success = False
        print(f"Database error: {e}")
    finally:
        cursor.close()
        conn.close()

    return jsonify({'success': success})

# --- Route 3: Add a New Job ---
@app.route('/add_job', methods=['POST'])
def add_job():
    data = request.get_json()
    job_number = data.get('job_number')
    customer_id = data.get('customer_id')
    title = data.get('title')
    finished_size = data.get('finished_size')
    paper_stock = data.get('paper_stock')
    delivery_date = data.get('delivery_date')
    date_received = data.get('date_received')
    quantity = data.get('quantity')
    ink = data.get('ink')
    finishing = data.get('finishing')
    price = data.get('price')

    customer_id = int(customer_id) if customer_id else None

    if not job_number or not title:
        return jsonify({'success': False, 'error': 'Job number and title are required.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO jobs (
                job_number, customer_id, title, finished_size, paper_stock, 
                delivery_date, date_received, quantity, ink, finishing, price, current_stage
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'booked in')
        ''', (job_number, customer_id, title, finished_size, paper_stock, 
              delivery_date, date_received, quantity, ink, finishing, price))
        
        cursor.execute('INSERT INTO status_logs (job_number, stage) VALUES (%s, %s)', (job_number, 'booked in'))
        success = True
    except psycopg2.IntegrityError:
        return jsonify({'success': False, 'error': 'Job number already exists.'}), 400
    except Exception as e:
        success = False
        print(f"Database error: {e}")
    finally:
        cursor.close()
        conn.close()
    return jsonify({'success': success})


# --- Route 4: Edit an Existing Job ---
@app.route('/update_job', methods=['POST'])
def update_job():
    data = request.get_json()
    job_number = data.get('job_number')
    customer_id = data.get('customer_id')
    title = data.get('title')
    finished_size = data.get('finished_size')
    paper_stock = data.get('paper_stock')
    delivery_date = data.get('delivery_date')
    date_received = data.get('date_received')
    quantity = data.get('quantity')
    ink = data.get('ink')
    finishing = data.get('finishing')
    price = data.get('price')

    customer_id = int(customer_id) if customer_id else None

    if not job_number:
        return jsonify({'success': False, 'error': 'Job number missing.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE jobs 
            SET customer_id = %s, title = %s, finished_size = %s, paper_stock = %s, 
                delivery_date = %s, date_received = %s, quantity = %s, ink = %s, finishing = %s, price = %s
            WHERE job_number = %s
        ''', (customer_id, title, finished_size, paper_stock, 
              delivery_date, date_received, quantity, ink, finishing, price, job_number))
        success = True
    except Exception as e:
        success = False
        print(f"Database error: {e}")
    finally:
        cursor.close()
        conn.close()
    return jsonify({'success': success})

# --- Route 5: The Customers Page ---
@app.route('/customers')
def customers():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('SELECT * FROM customers ORDER BY company_name')
    all_customers = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('customers.html', customers=all_customers)

# --- Route 6: Add a New Customer ---
@app.route('/add_customer', methods=['POST'])
def add_customer():
    data = request.get_json()
    
    company_name = data.get('company_name')
    contact_name = data.get('contact_name')
    primary_job_title = data.get('primary_job_title')
    email = data.get('email')
    primary_phone = data.get('primary_phone')
    
    secondary_contact_name = data.get('secondary_contact_name')
    secondary_job_title = data.get('secondary_job_title')
    secondary_email = data.get('secondary_email')
    secondary_phone = data.get('secondary_phone')

    if not company_name:
        return jsonify({'success': False, 'error': 'Company name is required.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO customers (
                company_name, contact_name, primary_job_title, email, primary_phone,
                secondary_contact_name, secondary_job_title, secondary_email, secondary_phone
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (company_name, contact_name, primary_job_title, email, primary_phone,
              secondary_contact_name, secondary_job_title, secondary_email, secondary_phone))
        success = True
    except Exception as e:
        success = False
        print(f"Database error: {e}")
    finally:
        cursor.close()
        conn.close()

    return jsonify({'success': success})

# --- Route 7: Client Profile Page ---
@app.route('/customer/<int:customer_id>')
def customer_profile(customer_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('SELECT * FROM customers WHERE id = %s', (customer_id,))
    customer = cursor.fetchone()
    
    cursor.execute('''
        SELECT * FROM jobs 
        WHERE customer_id = %s 
        ORDER BY job_number DESC
    ''', (customer_id,))
    jobs = cursor.fetchall()
    
    cursor.execute('''
        SELECT paper_stock, COUNT(paper_stock) as count 
        FROM jobs 
        WHERE customer_id = %s AND paper_stock != '' AND paper_stock IS NOT NULL
        GROUP BY paper_stock 
        ORDER BY count DESC 
        LIMIT 3
    ''', (customer_id,))
    top_stocks = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    if customer is None:
        return "<script>window.location.href='/customers';</script>"
        
    return render_template('customer_profile.html', customer=customer, jobs=jobs, top_stocks=top_stocks)


# --- Route 8: Live-Save Notes ---
@app.route('/update_notes', methods=['POST'])
def update_notes():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data received'}), 400
        
    customer_id = data.get('customer_id')
    notes = data.get('notes')

    if not customer_id:
        return jsonify({'success': False, 'error': 'Missing customer ID'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE customers SET notes = %s WHERE id = %s', (notes, customer_id))
        success = True
    except Exception as e:
        success = False
        print(f"Database error on notes update: {e}")
    finally:
        cursor.close()
        conn.close()

    return jsonify({'success': success})

# --- Route 9: Edit Existing Customer ---
@app.route('/edit_customer', methods=['POST'])
def edit_customer():
    data = request.get_json()
    customer_id = data.get('customer_id')
    
    if not customer_id:
        return jsonify({'success': False, 'error': 'Customer ID missing.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE customers SET 
                company_name = %s, contact_name = %s, primary_job_title = %s, email = %s, primary_phone = %s,
                secondary_contact_name = %s, secondary_job_title = %s, secondary_email = %s, secondary_phone = %s
            WHERE id = %s
        ''', (
            data.get('company_name'), data.get('contact_name'), data.get('primary_job_title'), 
            data.get('email'), data.get('primary_phone'), data.get('secondary_contact_name'), 
            data.get('secondary_job_title'), data.get('secondary_email'), data.get('secondary_phone'), 
            customer_id
        ))
        success = True
    except Exception as e:
        success = False
        print(f"Database error: {e}")
    finally:
        cursor.close()
        conn.close()

    return jsonify({'success': success})

# --- Route 10: Job Archive Page ---
@app.route('/job_archive')
def job_archive():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('''
        SELECT jobs.*, customers.company_name 
        FROM jobs 
        LEFT JOIN customers ON jobs.customer_id = customers.id
        WHERE jobs.current_stage = 'paid'
        ORDER BY job_number DESC
    ''')
    jobs = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('job_archive.html', jobs=jobs)

# --- Route 11: Return Jobs to Pipeline ---
@app.route('/return_to_pipeline', methods=['POST'])
def return_to_pipeline():
    data = request.get_json()
    job_numbers = data.get('job_numbers', [])

    if not job_numbers:
        return jsonify({'success': False, 'error': 'No jobs selected.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for job_num in job_numbers:
            cursor.execute('''
                UPDATE jobs SET current_stage = 'booked in' WHERE job_number = %s
            ''', (job_num,))
            cursor.execute('''
                INSERT INTO status_logs (job_number, stage) VALUES (%s, 'booked in')
            ''', (job_num,))
            
        success = True
    except Exception as e:
        success = False
        print(f"Database error: {e}")
    finally:
        cursor.close()
        conn.close()

    return jsonify({'success': success})

# --- Route 12: Delete a Customer ---
@app.route('/delete_customer/<int:customer_id>', methods=['DELETE'])
def delete_customer(customer_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Safely unlink this customer's existing jobs so they stay on the board
        cursor.execute('UPDATE jobs SET customer_id = NULL WHERE customer_id = %s', (customer_id,))
        # Delete the customer profile
        cursor.execute('DELETE FROM customers WHERE id = %s', (customer_id,))
        success = True
    except Exception as e:
        success = False
        print(f"Database error on delete: {e}")
    finally:
        cursor.close()
        conn.close()

    return jsonify({'success': success})

# --- Route 13: Export Master Database to CSV ---
@app.route('/export_csv')
def export_csv():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Fetch ALL jobs (active and archived) and join their customer data
    cursor.execute('''
        SELECT jobs.*, customers.company_name, customers.contact_name, customers.email, customers.primary_phone
        FROM jobs
        LEFT JOIN customers ON jobs.customer_id = customers.id
        ORDER BY jobs.date_received DESC
    ''')
    jobs = cursor.fetchall()
    cursor.close()
    conn.close()

    # Create the CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write the spreadsheet column headers
    writer.writerow([
        'Job Number', 'Company Name', 'Contact Name', 'Email', 'Phone',
        'Job Title', 'Current Stage', 'Date Received', 'Delivery Date',
        'Quantity', 'Finished Size', 'Paper Stock', 'Ink', 'Finishing', 'Price (£)'
    ])
    
    # Write the data rows
    for job in jobs:
        writer.writerow([
            job['job_number'], 
            job['company_name'] or 'No Client Linked', 
            job['contact_name'] or '', 
            job['email'] or '', 
            job['primary_phone'] or '',
            job['title'] or '', 
            job['current_stage'].upper() if job['current_stage'] else '', 
            job['date_received'] or '', 
            job['delivery_date'] or '',
            job['quantity'] or '', 
            job['finished_size'] or '', 
            job['paper_stock'] or '', 
            job['ink'] or '', 
            job['finishing'] or '', 
            job['price'] or ''
        ])
        
    # Stream the file to the browser
    response = Response(output.getvalue(), mimetype='text/csv')
    filename = f"GoWise_Print_Backup_{date.today().isoformat()}.csv"
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


# --- Route 14: Job Bible ---
@app.route('/job_bible')
def job_bible():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('SELECT id, company_name FROM customers ORDER BY company_name ASC')
    customers = cursor.fetchall()
    
    cursor.execute('''
        SELECT DISTINCT ON (customer_id, LOWER(title)) 
               customer_id, title, notes 
        FROM jobs 
        WHERE title IS NOT NULL AND title != ''
        ORDER BY customer_id, LOWER(title), date_received DESC
    ''')
    jobs = cursor.fetchall()
    
    # Format notes into clean lists for the frontend
    for job in jobs:
        raw_notes = job['notes']
        if raw_notes and str(raw_notes).strip().lower() != 'none':
            try:
                job['notes'] = json.loads(raw_notes)
            except:
                job['notes'] = [raw_notes] # Protects and converts any older text notes
        else:
            job['notes'] = []
            
    cursor.close()
    conn.close()
    
    return render_template('job_bible.html', customers=customers, jobs=jobs)

# --- Route 15: Save Job Notes ---
@app.route('/save_job_note', methods=['POST'])
def save_job_note():
    data = request.get_json()
    customer_id = data.get('customer_id')
    title = data.get('title')
    new_note = data.get('note')

    if not customer_id or not title or not new_note:
        return jsonify({'success': False}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT notes FROM jobs WHERE customer_id = %s AND LOWER(title) = LOWER(%s) LIMIT 1', (customer_id, title))
        row = cursor.fetchone()
        raw_notes = row[0] if row else None
        
        notes_list = []
        if raw_notes and str(raw_notes).strip().lower() != 'none':
            try:
                notes_list = json.loads(raw_notes)
            except:
                notes_list = [raw_notes]
                
        # Append the new note directly beneath
        notes_list.append(new_note)
        updated_notes_json = json.dumps(notes_list)

        cursor.execute('UPDATE jobs SET notes = %s WHERE customer_id = %s AND LOWER(title) = LOWER(%s)', (updated_notes_json, customer_id, title))
        success = True
    except Exception as e:
        success = False
        notes_list = []
    finally:
        cursor.close()
        conn.close()

    return jsonify({'success': success, 'updated_notes': notes_list})

# --- Route 16: Delete Job Note ---
@app.route('/delete_job_note', methods=['POST'])
def delete_job_note():
    data = request.get_json()
    customer_id = data.get('customer_id')
    title = data.get('title')
    note_index = data.get('index')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT notes FROM jobs WHERE customer_id = %s AND LOWER(title) = LOWER(%s) LIMIT 1', (customer_id, title))
        row = cursor.fetchone()
        raw_notes = row[0] if row else None
        
        notes_list = []
        if raw_notes and str(raw_notes).strip().lower() != 'none':
            try:
                notes_list = json.loads(raw_notes)
            except:
                notes_list = [raw_notes]
        
        # Remove the specific note based on the X clicked
        if 0 <= note_index < len(notes_list):
            notes_list.pop(note_index)
            
        updated_notes_json = json.dumps(notes_list)
        cursor.execute('UPDATE jobs SET notes = %s WHERE customer_id = %s AND LOWER(title) = LOWER(%s)', (updated_notes_json, customer_id, title))
        success = True
    except Exception as e:
        success = False
        notes_list = []
    finally:
        cursor.close()
        conn.close()
        
    return jsonify({'success': success, 'updated_notes': notes_list})


# --- Route 17: Add Job Bible Category ---
@app.route('/add_bible_category', methods=['POST'])
def add_bible_category():
    data = request.get_json()
    job_number = data.get('job_number')
    customer_id = data.get('customer_id')
    title = data.get('title')

    if not job_number or not title:
        return jsonify({'success': False, 'error': 'Missing data'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Set stage to 'bible' so it is ignored by the main pipeline board
        cursor.execute('''
            INSERT INTO jobs (job_number, customer_id, title, current_stage)
            VALUES (%s, %s, %s, 'bible')
        ''', (job_number, customer_id, title))
        
        cursor.execute('INSERT INTO status_logs (job_number, stage) VALUES (%s, %s)', (job_number, 'bible'))
        success = True
    except Exception as e:
        success = False
        print(f"Database error: {e}")
    finally:
        cursor.close()
        conn.close()

    return jsonify({'success': success})

# --- Route 18: Delete a Job (Pipeline & Archive) ---
@app.route('/delete_job/<job_number>', methods=['DELETE'])
def delete_job(job_number):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Delete from logs first to prevent foreign key constraint errors
        cursor.execute('DELETE FROM status_logs WHERE job_number = %s', (job_number,))
        cursor.execute('DELETE FROM jobs WHERE job_number = %s', (job_number,))
        success = True
    except Exception as e:
        success = False
        print(f"Database error on job delete: {e}")
    finally:
        cursor.close()
        conn.close()

    return jsonify({'success': success})

# --- Route 19: Delete a Category (Job Bible) ---
@app.route('/delete_bible_category', methods=['POST'])
def delete_bible_category():
    data = request.get_json()
    customer_id = data.get('customer_id')
    title = data.get('title')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Deletes all dummy category entries associated with this specific title and client
        cursor.execute('DELETE FROM jobs WHERE customer_id = %s AND LOWER(title) = LOWER(%s)', (customer_id, title))
        success = True
    except Exception as e:
        success = False
        print(f"Database error on category delete: {e}")
    finally:
        cursor.close()
        conn.close()

    return jsonify({'success': success})

# --- Route 20: Edit Job Note ---
@app.route('/edit_job_note', methods=['POST'])
def edit_job_note():
    data = request.get_json()
    customer_id = data.get('customer_id')
    title = data.get('title')
    note_index = data.get('index')
    updated_text = data.get('text')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT notes FROM jobs WHERE customer_id = %s AND LOWER(title) = LOWER(%s) LIMIT 1', (customer_id, title))
        row = cursor.fetchone()
        raw_notes = row[0] if row else None
        
        notes_list = []
        if raw_notes and str(raw_notes).strip().lower() != 'none':
            try:
                notes_list = json.loads(raw_notes)
            except:
                notes_list = [raw_notes]
        
        # Update the specific note based on the index
        if 0 <= note_index < len(notes_list):
            notes_list[note_index] = updated_text
            
        updated_notes_json = json.dumps(notes_list)
        cursor.execute('UPDATE jobs SET notes = %s WHERE customer_id = %s AND LOWER(title) = LOWER(%s)', (updated_notes_json, customer_id, title))
        success = True
    except Exception as e:
        success = False
        notes_list = []
    finally:
        cursor.close()
        conn.close()
        
    return jsonify({'success': success, 'updated_notes': notes_list})

# --- Route 21: Get Job Stage History ---
@app.route('/api/job_history/<job_number>', methods=['GET'])
def get_job_history(job_number):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Fetch the history AND the unique ID for deletion
        cursor.execute('''
            SELECT id, stage, created_at 
            FROM status_logs 
            WHERE job_number = %s 
            ORDER BY created_at ASC
        ''', (job_number,))
        history = cursor.fetchall()
        
        # Format the timestamps for the frontend
        for entry in history:
            if 'created_at' in entry and entry['created_at']:
                if isinstance(entry['created_at'], datetime):
                    entry['created_at'] = entry['created_at'].strftime("%d %b, %H:%M")
                elif isinstance(entry['created_at'], str):
                    entry['created_at'] = entry['created_at'][:16].replace('T', ' ')
                    
        success = True
    except Exception as e:
        success = False
        history = []
        print(f"Database error fetching history: {e}")
    finally:
        cursor.close()
        conn.close()

    return jsonify({'success': success, 'history': history})

# --- Route 22: Delete a Stage History Entry ---
@app.route('/delete_job_history/<int:log_id>', methods=['DELETE'])
def delete_job_history(log_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM status_logs WHERE id = %s', (log_id,))
        success = True
    except Exception as e:
        success = False
        print(f"Database error on history delete: {e}")
    finally:
        cursor.close()
        conn.close()

    return jsonify({'success': success})


# --- SERVER EXECUTION ---
def open_browser():
    os.system("open http://127.0.0.1:5002")

if __name__ == '__main__':
    multiprocessing.freeze_support()
    Timer(1, open_browser).start()
    # Host is set to 0.0.0.0 to allow network/Tailscale access
    app.run(host='0.0.0.0', debug=False, port=5002, use_reloader=False)