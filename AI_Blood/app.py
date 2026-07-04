# ================================================================
# PROJECT: AI BLOOD CARE SYSTEM
# CORE: FLASK APPLICATION (app.py)
# ================================================================

import csv
import io
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import sqlite3
from datetime import datetime
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, Response, flash
from database.db import get_db_connection
from models.predict import predict_disease
import pickle
import os
from werkzeug.utils import secure_filename
from flask import request, redirect, url_for, flash, session
from dateutil import parser
with open('models/allocation_model.pkl', 'rb') as f:
    allocation_model = pickle.load(f)
try:
    with open('models/shortage_model.pkl', 'rb') as f:
        ai_model = pickle.load(f)
except Exception as e:
    print(f"Warning: AI Model not loaded. {e}")
    ai_model = None


try:
    with open('models/shortage_model.pkl', 'rb') as f:
        ai_model = pickle.load(f)
except Exception as e:
    print(f"Warning: AI Model not loaded. {e}")
    ai_model = None


app = Flask(__name__)
app.secret_key = "blood_care_secret_key"
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# ------------------ GLOBAL SETTINGS ------------------
# Default donation recovery period (can be changed by admin)
GLOBAL_DONATION_PERIOD = 90 


# ------------------ SECURITY HELPER FUNCTIONS ------------------
def is_logged_in():
    return 'user' in session

def is_admin():
    return session.get('role') == 'admin'


def send_emergency_alert(donor_name, blood_group):
    # --- SETUP YOUR CREDENTIALS HERE ---
    sender_email = "your_actual_gmail_address@gmail.com" # <-- Put your Gmail here!
    app_password = "avggunejiceoyodo" 
    
    receiver_email = "aneraodhanashri32@gmail.com, rharipriya070@gmail.com, kmanasi301@gmail.com" 

    email_body = f"EMERGENCY OVERRIDE TRIGGERED.\n\nDonor {donor_name} ({blood_group}) has been manually approved for an emergency bypass of the standard 90-day waiting period."
    msg = MIMEText(email_body)
    msg['Subject'] = f"🚨 URGENT: Emergency Blood Override - {donor_name} ({blood_group})"
    msg['From'] = sender_email
    msg['To'] = receiver_email

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls() 
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()
        print(f"Success: Emergency email sent for {donor_name}!")
    except Exception as e:
        print(f"Error sending email: {e}")

# ------------------ AUTHENTICATION (LOGIN/LOGOUT) ------------------
@app.route("/", methods=['GET', 'POST'])
@app.route("/login", methods=['GET', 'POST'])
def login():
    if is_logged_in():
        return redirect(url_for('admin' if is_admin() else 'donor_portal'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 🔥 UPDATE: Select 'role' and 'fullname' so we can use them in the session
        cursor.execute("SELECT username, role, fullname FROM users WHERE username=? AND password=?", (username, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session['user'] = user[2]  # fullname
            session['role'] = user[1]  # role ('admin' or 'donor')
    
            if user[1] == 'admin':
                return redirect(url_for('admin')) # Points to your def admin():
            else:
                return redirect(url_for('donor_portal')) # Points to your donor portal
        else:
            return render_template("auth.html", error="Invalid Credentials")

    return render_template("auth.html")

@app.route('/register')
def register():
    # Show the registration version of the SAME auth.html
    return render_template('auth.html', mode='register')

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

# ------------------ NEW USER REGISTRATION ------------------
@app.route('/register_user', methods=['POST'])
def register_user():
    # 1. Get all data from the form
    fullname = request.form.get('fullname')
    username = request.form.get('username')
    password = request.form.get('password')
    blood_group = request.form.get('blood_group')
    weight = request.form.get('weight')
    phone = request.form.get('phone')
    age = request.form.get('age')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 2. Create the Login Account
        cursor.execute("""
            INSERT INTO users (fullname, username, password, role) 
            VALUES (?, ?, ?, 'User')
        """, (fullname, username, password))

        # 3. Create the Medical Profile IMMEDIATELY (The Fix!)
        # This ensures the 'donor_portal' finds a record for new users too
        cursor.execute("""
            INSERT INTO donors (fullname, blood_group, weight, phone, age, status) 
            VALUES (?, ?, ?, ?, ?, 'Eligible')
        """, (fullname, blood_group, weight, phone, age))

        conn.commit()
        flash("Registration Successful! Please Login.", "success")
        return redirect(url_for('login'))

    except Exception as e:
        conn.rollback()
        return f"Error: {str(e)}"
    finally:
        conn.close()

# ------------------ USER PROFILE ------------------
@app.route("/profile")
def profile():
    if not is_logged_in():
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT fullname FROM users WHERE username=?", (session['user'],))
    user = cursor.fetchone()
    conn.close()

    return render_template("profile.html", name=user[0] if user else session['user'])


@app.route('/update_profile', methods=['POST'])
def update_profile():
    # 1. Security Check
    if not is_logged_in():
        return redirect(url_for('login'))

    # 2. Grab the data from the HTML Modal
    full_name = request.form.get('full_name')
    phone = request.form.get('phone') # Changed to match your DB
    current_username = session['user']

    # 3. Update the Database
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 🌟 EXACT MATCH FOR YOUR SQL SERVER SCHEMA 🌟
        cursor.execute("""
            UPDATE users 
            SET fullname = ?, phone = ? 
            WHERE username = ?
        """, (full_name, phone, current_username))
        
        conn.commit()
        flash("Profile details updated successfully!", "success")
        
    except Exception as e:
        flash(f"An error occurred: {str(e)}", "danger")
        
    finally:
        conn.close()

    # 4. Send them right back to their profile page
    return redirect(url_for('profile'))

# ------------------ HEALTH CHECK & ML PREDICTION ------------------
@app.route("/health")
def health():
    if not is_logged_in():
        return redirect(url_for('login'))
    return render_template("health_check.html")

@app.route("/predict", methods=['POST'])
def predict():
    if not is_logged_in():
        return redirect(url_for('login'))

    try:
        hb = float(request.form.get('hb'))
        rbc = float(request.form.get('rbc'))
        wbc = float(request.form.get('wbc'))
        plt = float(request.form.get('platelets'))

        result = predict_disease(hb, rbc, wbc, plt)
        return render_template("result.html", result=result)
    except (ValueError, TypeError):
        flash("Please enter valid numeric values.", "error")
        return redirect(url_for('health'))


# ------------------ EMERGENCY BLOOD REQUESTS ------------------
@app.route("/request")
def request_page():
    if not is_logged_in(): return redirect(url_for('login'))
    return render_template("request.html")

@app.route("/submit_request", methods=['POST'])
def submit_request():
    if not is_logged_in(): 
        return redirect(url_for('login'))

    name = session['user']
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. ANTI-SPAM PROTOCOL
    cursor.execute("""
        SELECT COUNT(*) FROM blood_requests_admin 
        WHERE RTRIM(name) = RTRIM(?) AND status IN ('Pending', 'Approved')
    """, (name,))
    if cursor.fetchone()[0] > 0:
        flash("Anti-Spam: You already have an active request.", "warning")
        return redirect(url_for('request_status'))

    # 2. GET FORM DATA
    hospital = request.form.get('hospital')
    group = request.form.get('blood_group')
    units = int(request.form.get('units'))
    contact = request.form.get('contact')
    patient_name = request.form.get('patient_name')
    patient_age = request.form.get('patient_age')
    aadhaar_no = request.form.get('aadhaar_no')
    is_emergency = request.form.get('is_emergency')
    priority = 'Emergency' if is_emergency else 'Normal'

    # 🔥 2.5 STRICT BACKEND VALIDATION
    if not contact or not contact.isdigit() or len(contact) != 10:
        flash("Request failed: Contact number must be exactly 10 digits.", "danger")
        return redirect(url_for('request_page'))

    if not aadhaar_no or not aadhaar_no.isdigit() or len(aadhaar_no) != 12:
        flash("Request failed: Aadhaar number must be exactly 12 digits.", "danger")
        return redirect(url_for('request_page'))

    # 3. SAVE UPLOADED ID PROOF
    id_proof_path = None
    if 'id_proof' in request.files:
        file = request.files['id_proof']
        if file and file.filename != '':
            filename = secure_filename(f"{name}_{file.filename}")
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            id_proof_path = filepath

    # 4. EMERGENCY AUTO-APPROVE LOGIC
    status = "Pending"
    if priority == 'Emergency':
        cursor.execute("SELECT units FROM blood_stock WHERE blood_group=?", (group,))
        result = cursor.fetchone()
        available = result[0] if result else 0

        if available >= units:
            status = "Approved"
            cursor.execute("UPDATE blood_stock SET units = units - ? WHERE blood_group = ?", (units, group))
            flash("🚨 Emergency request AUTO-APPROVED!", "danger")
        else:
            status = "Rejected"
            flash("❌ Not enough stock for emergency!", "danger")
    else:
        flash("Request submitted successfully.", "success")

    # 5. INSERT INTO DATABASE
    cursor.execute("""
        INSERT INTO blood_requests_admin 
        (name, hospital, blood_group, units, status, contact, priority, patient_name, patient_age, aadhaar_no, id_proof_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, hospital, group, units, status, contact, priority, patient_name, patient_age, aadhaar_no, id_proof_path))

    conn.commit()
    conn.close()

    # 6. REDIRECT
    if priority == 'Emergency':
        return redirect(url_for('alerts'))
    else:
        return redirect(url_for('request_status'))

@app.route("/request_status")
def request_status():
    if not is_logged_in(): return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    # Fetch only the logged-in user's requests to show their history
    cursor.execute("""
        SELECT hospital, blood_group, units, priority, status 
        FROM blood_requests_admin 
        WHERE RTRIM(name) = RTRIM(?) ORDER BY id DESC
    """, (session['user'],))
    user_history = cursor.fetchall()
    conn.close()
    
    # Map raw data to dictionary for easier template use
    history_data = [
        {'hospital': r[0], 'blood_group': r[1], 'units': r[2], 'priority': r[3], 'status': r[4]} 
        for r in user_history
    ]
    
    return render_template("request_status.html", user_history=history_data)

# The Alerts route (your existing alerts route may need updating to render the full page)
@app.route("/emergency_alerts")
def emergency_alerts():
    if not is_logged_in(): return redirect(url_for('login'))
    return render_template("alerts.html")

# ------------------ USER DASHBOARD ------------------
@app.route("/dashboard")
def dashboard():
    # 1. Check if logged in
    if not is_logged_in():
        return redirect(url_for('login'))

    # 2. Get the current user's name from the session
    current_user = session.get('user')

    conn = get_db_connection()
    cursor = conn.cursor()

    # 🔥 NEW LOGIC: Count ONLY the logged-in user's donations from history
    try:
        cursor.execute("SELECT COUNT(*) FROM donor_history WHERE donor_name = ?", (current_user,))
        user_donation_count = cursor.fetchone()[0]
    except Exception as e:
        print(f"Error fetching donation count: {e}")
        user_donation_count = 0

    # Fetch all blood stock
    cursor.execute("SELECT blood_group, units FROM blood_stock")
    rows = cursor.fetchall()
    
    # Close connection early since we have all the data we need
    conn.close()

    inventory = []
    alerts_count = 0

    # 3. Clean, single loop for processing inventory data
    for g, u in rows:
        # Calculate progress bar width (capped at 100)
        percentage = int((u / 1000) * 100)
        width = min(percentage, 100) 
        
        # Set badge colors, text status, and track alerts based on stock amount
        if u <= 150:
            status = 'Critical'
            color = 'danger'     # Red
            alerts_count += 1    # Trigger an alert for critical stock
        elif u <= 400:
            status = 'Stable'
            color = 'warning'    # Yellow
        else:
            status = 'Optimal'
            color = 'success'    # Green
            
        inventory.append({
            'group': g, 
            'units': u, 
            'status': status,
            'width': width,
            'color': color
        })

    # 4. AI Prediction Logic
    ai_status = "PENDING"
    ai_color = "secondary"
    ai_message = "AI model initializing..."
    ai_prob = 0

    if ai_model is not None:
        try:
            total_stock = sum(item['units'] for item in inventory)
            features = [[total_stock, 50, 5]]
            probability = ai_model.predict_proba(features)[0][1] * 100
            ai_prob = int(probability)
            
            if ai_prob >= 70:
                ai_status = "CRITICAL RISK"
                ai_color = "danger"
                ai_message = "High probability of shortage in next 7 days."
            elif ai_prob >= 40:
                ai_status = "MODERATE RISK"
                ai_color = "warning"
                ai_message = "Stock is decreasing. Monitor incoming requests."
            else:
                ai_status = "STABLE"
                ai_color = "success"
                ai_message = "Inventory levels are healthy."
        except Exception as e:
            print(f"AI Prediction Error: {e}")
            
    # 5. Pass the specific user_donation_count to the template
    return render_template("dashboard.html", 
                           user_donation_count=user_donation_count, 
                           inventory=inventory, 
                           alerts_count=alerts_count, 
                           ai_status=ai_status,
                           ai_color=ai_color,
                           ai_message=ai_message,
                           ai_prob=ai_prob)

# ------------------ USER SIDE: DONOR PORTAL & REGISTRATION ------------------
from datetime import datetime

@app.route('/donor_portal')
def donor_portal():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    current_user = session['user']
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Fetch Profile
    cursor.execute("SELECT * FROM donors WHERE fullname = ?", (current_user,))
    donor = cursor.fetchone()
    
    # 2. Fetch History
    cursor.execute("""
        SELECT hospital, units, donation_date 
        FROM donor_history 
        WHERE donor_name = ? 
        ORDER BY donation_date DESC
    """, (current_user,))
    history = cursor.fetchall()
    
    can_donate = True
    days_left = 0
    next_date = None  # Master initialization

    if donor and donor[8]: # Index 8 is last_donation
        try:
            # Handles VARCHAR dates like "May 11 2026"
            last_date = parser.parse(str(donor[8])).replace(tzinfo=None)
            diff = (datetime.now() - last_date).days
            
            if diff < 90:
                can_donate = False
                days_left = 90 - diff
                # Calculate the exact date for the HTML to display
                next_date_obj = last_date + timedelta(days=90)
                next_date = next_date_obj.strftime('%d %b, %Y')
        except Exception as e:
            print(f"Date Error: {e}")

    return render_template('donors.html', 
                       donor=donor, 
                       history=history, 
                       can_donate=can_donate, 
                       days_left=days_left,
                       next_date=next_date)

@app.route('/register_donor_action', methods=['POST'])
def register_donor_action():
    if 'user' not in session:
        return redirect(url_for('login'))

    # 🔥 FIX: Force the name to be the session user so they ALWAYS match
    name = session['user'] 
    blood_group = request.form.get('blood_group')
    age = request.form.get('age')
    weight = request.form.get('weight')
    phone = request.form.get('phone')
    gender = request.form.get('gender', 'Not Specified')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO donors (fullname, blood_group, gender, age, weight, last_donation, phone, status)
            VALUES (?, ?, ?, ?, ?, NULL, ?, 'Eligible')
        """, (name, blood_group, gender, age, weight, phone))
        
        conn.commit()
        flash("Registration Successful! Welcome to the Donor Club.", "success")
    except Exception as e:
        print(f"DB ERROR: {e}")
        flash("Registration failed. Name might already exist.", "danger")
    finally:
        conn.close()

    return redirect(url_for('donor_portal'))

@app.route('/submit_donation', methods=['POST'])
def submit_donation():
    if 'user' not in session:
        return redirect(url_for('login'))

    fullname = session.get('user')
    hospital = request.form.get('hospital')
    units = request.form.get('units')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # A. Record in History (Column 'donor_name')
        cursor.execute("""
            INSERT INTO donor_history (donor_name, hospital, units, donation_date, status) 
            VALUES (?, ?, ?, GETDATE(), 'Verified')
        """, (fullname, hospital, units))
        
        # B. Start 90-day timer (Column 'fullname')
        # Using standardized format for the update
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("UPDATE donors SET last_donation = ? WHERE fullname = ?", (current_time, fullname))
        
        conn.commit()
        flash("Success! Donation recorded and recovery phase started.", "success")
    except Exception as e:
        print(f"Submission Error: {e}")
        flash("Error recording donation.", "danger")
    finally:
        conn.close()

    return redirect(url_for('donor_portal'))

#------------------ ADMIN DASHBOARD & AI PREDICTION ------------------
# ------------------ ADMIN DASHBOARD ------------------
@app.route("/admin")
def admin():
    # 1. Security Check
    if not is_logged_in() or not is_admin(): 
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # 2. Fetch Top Metric Cards
    cursor.execute("SELECT COUNT(*) FROM donors")
    total_donors = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(units), 0) FROM blood_stock")
    total_stock = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM blood_requests_admin")
    total_requests = cursor.fetchone()[0]

    cursor.execute("SELECT TOP 5 * FROM blood_requests_admin ORDER BY id DESC")
    recent_requests = cursor.fetchall()

    # 3. Fetch Stock Data for AI & Charts
    cursor.execute("SELECT blood_group, units FROM blood_stock")
    stock_data = cursor.fetchall()
    
    # Required for the Chart.js graphs
    groups_list = [row[0] for row in stock_data]
    units_list = [row[1] for row in stock_data]
    
    detailed_stock = []
    
    # 4. Per-Blood-Group AI Prediction
    for row in stock_data:
        bg = row[0]
        current_stock = row[1]
        
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(units), 0) 
            FROM blood_requests_admin 
            WHERE blood_group = ? AND status = 'Pending'
        """, (bg,))
        req_data = cursor.fetchone()
        
        emergency_hits = req_data[0] 
        request_volume = req_data[1] 
        
        if ai_model:
            features = [[current_stock, request_volume, emergency_hits]]
            probabilities = ai_model.predict_proba(features)[0]
            
            if len(probabilities) > 1:
                prob = round(probabilities[1] * 100, 1) 
            else:
                known_class = ai_model.classes_[0]
                prob = 100.0 if known_class == 1 else 0.0
            
            if prob >= 70 or current_stock <= 2:
                risk_label = "CRITICAL"
                risk_color = "danger"
            elif prob >= 30:
                risk_label = "WARNING"
                risk_color = "warning"
            else:
                risk_label = "SAFE"
                risk_color = "success"
        else:
            prob = 0.0
            risk_label = "SAFE"
            risk_color = "success"

        detailed_stock.append({
            'group': bg,
            'stock': current_stock,
            'req_vol': request_volume,
            'hits': emergency_hits,
            'risk_label': risk_label,
            'risk_color': risk_color,
            'prob': prob
        })

    # 🔥 5. System-Wide AI Prediction (For the top Admin Widget)
    ai_status = "PENDING"
    ai_color = "secondary"
    ai_message = "AI model initializing..."
    ai_prob = 0

    if ai_model is not None:
        try:
            # Using the total_stock we fetched at the very beginning!
            features = [[total_stock, 50, 5]]
            probability = ai_model.predict_proba(features)[0][1] * 100
            ai_prob = int(probability)
            
            if ai_prob >= 70:
                ai_status = "CRITICAL RISK"
                ai_color = "danger"
                ai_message = "High probability of shortage in next 7 days."
            elif ai_prob >= 40:
                ai_status = "MODERATE RISK"
                ai_color = "warning"
                ai_message = "Stock is decreasing. Monitor incoming requests."
            else:
                ai_status = "STABLE"
                ai_color = "success"
                ai_message = "Inventory levels are healthy."
        except Exception as e:
            print(f"Overall AI Prediction Error: {e}")

    conn.close()
    
    # 6. Pass EVERYTHING to the Admin Template
    return render_template("admin/admin.html", 
                           donors=total_donors, 
                           stock=total_stock, 
                           requests=total_requests,
                           recent_requests=recent_requests,
                           groups=groups_list,
                           units=units_list,
                           detailed_stock=detailed_stock,
                           ai_status=ai_status,
                           ai_color=ai_color,
                           ai_message=ai_message,
                           ai_prob=ai_prob)

@app.route("/admin/update_period", methods=['POST'])
def update_period():
    if not (is_logged_in() and is_admin()): return redirect(url_for('login'))
    
    global GLOBAL_DONATION_PERIOD
    new_period = request.form.get('donation_period', type=int)
    
    if new_period and new_period > 0:
        GLOBAL_DONATION_PERIOD = new_period
        flash(f'Success! Blood donation recovery period updated to {new_period} days.', 'success')
    else:
        flash('Invalid period entered. Must be greater than 0.', 'danger')
        
    return redirect(url_for('admin'))


# ------------------ ADMIN: DONOR MANAGEMENT & OVERRIDES ------------------
@app.route("/admin/donors")
def donors():
    if not (is_logged_in() and is_admin()): return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, fullname, blood_group, phone, age, weight, gender FROM donors")
    rows = cursor.fetchall()
    conn.close()

    donors_list = []
    for r in rows:
        donors_list.append({
            'id': r[0], 'name': r[1], 'group': r[2], 'phone': r[3], 
            'age': r[4], 'weight': r[5], 'gender': r[6]
        })
    return render_template("admin/donors_admin.html", donors=donors_list)

@app.route("/admin/update_donor/<int:id>", methods=['POST'])
def update_donor(id):
    if not (is_logged_in() and is_admin()): return redirect(url_for('login'))
    
    name, group = request.form.get('name'), request.form.get('group')
    age, phone = request.form.get('age'), request.form.get('phone')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE donors SET fullname=?, blood_group=?, age=?, phone=? WHERE id=?", 
                   (name, group, age, phone, id))
    conn.commit()
    conn.close()
    
    flash("Donor updated successfully!", "success")
    return redirect(url_for('donors'))

@app.route("/admin/delete_donor/<int:id>", methods=['POST'])
def delete_donor(id):
    if not (is_logged_in() and is_admin()): return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM donors WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    
    flash("Donor deleted successfully!", "danger")
    return redirect(url_for('donors'))

@app.route("/admin/emergency_override/<int:id>", methods=['POST'])
def emergency_override(id):
    if not (is_logged_in() and is_admin()): return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Update the database to bypass the cooldown rule
    cursor.execute("UPDATE donors SET status='Emergency Bypass' WHERE id=?", (id,))
    
    # 2. Fetch their details to send the email
    cursor.execute("SELECT fullname, blood_group FROM donors WHERE id=?", (id,))
    donor = cursor.fetchone()
    conn.commit()
    conn.close()

    if donor:
        donor_name = donor[0]
        blood_group = donor[1]
        
        # --- EMAIL SENDING LOGIC ---
        try:
            msg = MIMEText(f"Dear {donor_name},\n\nWe have an extreme emergency for {blood_group} blood. We have overridden your waiting period. Please log into your portal and schedule a donation immediately if you are healthy.")
            msg['Subject'] = 'URGENT: Emergency Blood Request'
            msg['From'] = 'admin@bloodcare.com'
            msg['To'] = f'{donor_name}@example.com' 

            # server = smtplib.SMTP('smtp.gmail.com', 587)
            # server.starttls()
            # server.login("your_email@gmail.com", "your_app_password")
            # server.send_message(msg)
            # server.quit()
            
            flash(f"Emergency Override activated for {donor_name}. Email notification simulated successfully!", "success")
        except Exception as e:
            flash(f"Override activated, but failed to send email. Error: {str(e)}", "warning")

    return redirect(url_for('donors'))

@app.route("/admin/complete_donation/<int:donor_id>/<blood_group>")
def complete_donation(donor_id, blood_group):
    if not (is_logged_in() and is_admin()):
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Update Blood Stock (Addition)
        cursor.execute("""
            UPDATE blood_stock 
            SET units = units + 1 
            WHERE blood_group = ?
        """, (blood_group,))

        # 2. Update Donor Info in the 'donors' table
        from datetime import datetime
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute("""
            UPDATE donors 
            SET last_donation = ?, status = 'Eligible' 
            WHERE id = ?
        """, (current_time, donor_id))

        conn.commit()
        flash(f'Success! 1 unit added to {blood_group} stock.', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Database Error: {str(e)}', 'danger')
    finally:
        conn.close()

    # Redirects back to the donor list page
    return redirect(url_for('donors'))

# ------------------ ADMIN: REQUEST APPROVAL & INVENTORY UPDATE ------------------
@app.route("/admin/requests")
def admin_requests():

    if not (is_logged_in() and is_admin()):
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch requests with priority
    cursor.execute("""
        SELECT 
            id,
            name,
            hospital,
            blood_group,
            units,
            status,
            priority
        FROM blood_requests_admin
        ORDER BY id DESC
    """)

    rows = cursor.fetchall()

    conn.close()

    # Convert rows into dictionary
    requests_data = []

    for r in rows:
        requests_data.append({
            'id': r[0],
            'name': r[1],
            'hospital': r[2],
            'group': r[3],
            'units': r[4],
            'status': r[5],
            'priority': r[6]
        })

    return render_template(
        "admin/manage_requests.html",
        requests_data=requests_data
    )

@app.route("/approve_request/<int:request_id>")
def approve_request(request_id):
    if session.get('user') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Fetch details of the request first
        cursor.execute("SELECT blood_group, units FROM blood_requests_admin WHERE id = ?", (request_id,))
        req = cursor.fetchone()
        
        if req:
            blood_group = req[0]
            units_to_deduct = req[1]

            # 2. Update the Request Status
            cursor.execute("UPDATE blood_requests_admin SET status = 'Approved' WHERE id = ?", (request_id,))

            # 3. SUBTRACT from Blood Stock
            cursor.execute("""
                UPDATE blood_stock 
                SET units = units - ? 
                WHERE blood_group = ?
            """, (units_to_deduct, blood_group))

            conn.commit()
            flash(f"Request Approved. {units_to_deduct} units deducted from {blood_group} stock.", "success")
    except Exception as e:
        conn.rollback() # Undo changes if something fails
        flash(f"Error: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for('manage_requests'))
    if not (is_logged_in() and is_admin()): return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Fetch the request details
    cursor.execute("SELECT name, blood_group, units, status FROM blood_requests_admin WHERE id=?", (req_id,))
    req = cursor.fetchone()
    
    # Security Check: Only process 'Pending' requests
    if req and req[3] == 'Pending':
        donor_name = req[0]
        b_group = req[1]
        units_donated = float(req[2]) 
        
        # 2. Update the request status
        cursor.execute("UPDATE blood_requests_admin SET status='Approved' WHERE id=?", (req_id,))
        
        # 3. Add the donated units to the main blood_stock table
        cursor.execute("UPDATE blood_stock SET units = units + ? WHERE blood_group=?", (units_donated, b_group))
        
        # 4. Update the donor's last_donation date & reset Emergency status
        cursor.execute("""
            UPDATE donors 
            SET last_donation = ?, status = 'Eligible' 
            WHERE RTRIM(fullname) = RTRIM(?)
        """, (datetime.now(), donor_name))
        
        conn.commit()
        flash(f"Success! Donation approved. {units_donated} units added to {b_group} stock.", "success")
    else:
        flash("This request has already been processed or does not exist.", "warning")
        
    conn.close()
    return redirect(url_for('admin_requests'))


@app.route("/reject_request/<int:req_id>")
def reject_request(req_id):
    if not (is_logged_in() and is_admin()): return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE blood_requests_admin SET status='Rejected' WHERE id=?", (req_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_requests'))


# ------------------ STOCK & ALERTS ------------------
@app.route("/stock")
def blood_stock():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT blood_group, units FROM blood_stock")
        rows = cursor.fetchall()
        conn.close()
        
        stock_list = [{'group': r[0], 'units': r[1]} for r in rows]
        return render_template("blood_stock.html", stock=stock_list)
    except Exception as e:
        print(f"Error: {e}")
        # Always redirect to a valid function name
        return redirect(url_for('donor_portal'))

# ==========================================
#ADMIN ROUTE: Live Blood Stock & AI Warnings
# ==========================================

@app.route("/admin/stock")
def admin_stock():
    # 1. SECURITY: Uncommented to ensure only Admins can access this page!
    if not is_logged_in() or not is_admin():
        flash("Unauthorized access. Admin privileges required.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    blood_groups = ['A+', 'A-', 'B+', 'B-', 'O+', 'O-', 'AB+', 'AB-']
    stock = []
    low_groups = []
    
    # Base safety thresholds
    critical_level = 50  
    low_level = 150      

    # 2. Calculate the live inventory AND pending requests for the AI
    for bg in blood_groups:
        # A. Sum up all current units for this blood type
        cursor.execute("""
            SELECT ISNULL(SUM(units), 0) 
            FROM blood_stock 
            WHERE RTRIM(blood_group) = ?
        """, (bg,))
        total_units = cursor.fetchone()[0]

        # B. Get pending hospital requests for this group (Fuel for the AI)
        cursor.execute("""
            SELECT COUNT(*), ISNULL(SUM(units), 0) 
            FROM blood_requests_admin 
            WHERE blood_group = ? AND status = 'Pending'
        """, (bg,))
        req_data = cursor.fetchone()
        emergency_hits = req_data[0] 
        request_volume = req_data[1]

        # 3. TRUE AI PREDICTION LOGIC
        status = 'Stable'
        prob = 0.0

        if ai_model:
            # Feed the live data into your machine learning model
            features = [[total_units, request_volume, emergency_hits]]
            probabilities = ai_model.predict_proba(features)[0]
            
            if len(probabilities) > 1:
                prob = round(probabilities[1] * 100, 1)
            else:
                known_class = ai_model.classes_[0]
                prob = 100.0 if known_class == 1 else 0.0

            # Combine the ML prediction with your base thresholds
            if prob >= 70 or total_units <= critical_level:
                status = 'Critical'
                low_groups.append({'group': bg, 'risk': 'Critical Shortage Predicted'})
            elif prob >= 30 or total_units <= low_level:
                status = 'Low'
                low_groups.append({'group': bg, 'risk': 'Declining Stock'})
        else:
            # Fallback to standard logic if the AI model fails to load
            if total_units <= critical_level:
                status = 'Critical'
                low_groups.append({'group': bg, 'risk': 'Below Minimum Limit'})
            elif total_units <= low_level:
                status = 'Low'
                low_groups.append({'group': bg, 'risk': 'Approaching Minimum Limit'})

        # 4. Append the formatted data to our stock list
        stock.append({
            'group': bg,
            'units': total_units,
            'status': status,
            'ai_prob': prob  # Pass the exact percentage to the HTML!
        })

    conn.close()
    
    # 5. Render the Admin HTML template
    return render_template('admin/blood_stock.html', stock=stock, low_groups=low_groups)

# The Alerts route (completed and matching your redirect)
@app.route("/alerts")
def alerts():
    if not is_logged_in(): 
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Check if this specific user just submitted an Emergency request
    # We look for 'URGENT' or 'Emergency' just to be safe!
    current_user = session['user']
    cursor.execute("""
        SELECT blood_group, status 
        FROM blood_requests_admin 
        WHERE RTRIM(name) = RTRIM(?) AND priority IN ('URGENT', 'Emergency')
        ORDER BY id DESC
    """, (current_user,))
    
    active_req = cursor.fetchone()
    
    if active_req:
        # We found their active emergency!
        has_emergency = True
        blood_group = active_req[0]
        hospital_status = active_req[1]
        
        # 2. Count matching eligible donors using the wildcard LIKE search
        cursor.execute("SELECT COUNT(*) FROM donors WHERE blood_group LIKE ?", (f'%{blood_group}%',))
        notified_count = cursor.fetchone()[0]
        
    else:
        # No emergencies found for this user, show the green "System Normal" screen
        has_emergency = False
        blood_group = ""
        hospital_status = ""
        notified_count = 0
        
    conn.close()

    # 3. Pass all the data to your beautiful alerts.html page
    return render_template('alerts.html', 
                           has_emergency=has_emergency,
                           blood_group=blood_group,
                           notified_count=notified_count,
                           hospital_status=hospital_status)
    # If the user isn't logged in, send them to login
    if 'user' not in session: # Adjust this to match your actual session variable
        return redirect(url_for('login'))
    
    current_user = session['user'] 
    
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Find if this specific user has an active Emergency request
    cursor.execute("""
        SELECT TOP 1 blood_group, status 
        FROM blood_requests_admin 
        WHERE priority = 'Emergency'
        ORDER BY id DESC
    """) # You can add "AND user_name = ?" if you only want their specific alerts
    
    active_emergency = cursor.fetchone()
    
    notified_count = 0
    hospital_status = "No Active Requests"
    req_blood_group = None

    if active_emergency:
        req_blood_group = active_emergency[0]
        hospital_status = active_emergency[1]

        # 2. If there IS an emergency, count how many REAL donors match that blood type!
        cursor.execute("""
            SELECT COUNT(*) 
            FROM donors 
            WHERE RTRIM(blood_group) = ? AND status = 'Eligible'
        """, (req_blood_group,))
        notified_count = cursor.fetchone()[0]

    conn.close()

    # Pass all this live data to your HTML page
    return render_template('alerts.html', 
                           has_emergency=(active_emergency is not None),
                           blood_group=req_blood_group,
                           notified_count=notified_count,
                           hospital_status=hospital_status)

# ------------------ REPORTS & DATA EXPORT ------------------
@app.route("/report_status")
def report_status():
    if not is_logged_in(): return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(units) FROM blood_stock")
    total_units = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM donors")
    total_donors = cursor.fetchone()[0]
    conn.close()
    
    # Package the variables into a dictionary called 'stats'
    stats_data = {
        'total_units': total_units,
        'total_donors': total_donors
    }
    
    return render_template("report_success.html", stats=stats_data)

@app.route("/download_csv")
def download_csv():
    if not is_logged_in(): return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT blood_group, units FROM blood_stock")
    rows = cursor.fetchall()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Blood Group', 'Units'])
    for row in rows:
        writer.writerow(row)
    output.seek(0)
    
    return Response(output.getvalue(),
                    mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=report.csv"})

# ------------------ RUN APPLICATION ------------------
if __name__ == '__main__':
    # use_reloader=False prevents the WinError 10038 socket crash
    app.run(debug=True, use_reloader=False)
