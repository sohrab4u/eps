import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from reportlab.lib.pagesizes import A5
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io
import hashlib
import uuid
import time

# Initialize SQLite database and handle schema migration
def init_db():
    conn = None
    try:
        conn = sqlite3.connect('school.db', timeout=10)
        c = conn.cursor()
    
        # Create students table
        c.execute('''CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            first_name VARCHAR(50) NOT NULL,
            middle_name VARCHAR(50) DEFAULT '',
            last_name VARCHAR(50) NOT NULL,
            mother_name TEXT NOT NULL,
            father_name TEXT NOT NULL,
            address TEXT,
            email TEXT,
            mobile_number VARCHAR(15),
            dob TEXT,
            class_name VARCHAR(10),
            whatsapp_no TEXT,
            gender VARCHAR(20),
            doa TEXT,
            roll_number TEXT,
            outstanding_balance REAL DEFAULT 0.0,
            extra_balance REAL DEFAULT 0.0
        )''')
    
        # Check and drop tuition_fee, bus_fee, total_amount if they exist
        c.execute("PRAGMA table_info(students)")
        columns = [col[1] for col in c.fetchall()]
        if 'tuition_fee' in columns or 'bus_fee' in columns or 'total_amount' in columns:
            c.execute('''CREATE TABLE students_temp (
                student_id TEXT PRIMARY KEY,
                first_name VARCHAR(50) NOT NULL,
                middle_name VARCHAR(50),
                last_name VARCHAR(50) NOT NULL,
                mother_name TEXT,
                father_name TEXT,
                address TEXT,
                email TEXT,
                mobile_number VARCHAR(15),
                dob TEXT,
                class_name VARCHAR(10),
                whatsapp_no TEXT,
                gender VARCHAR(20),
                doa TEXT,
                roll_number TEXT,
                outstanding_balance REAL DEFAULT 0.0,
                extra_balance REAL DEFAULT 0.0
            )''')
            c.execute('''INSERT INTO students_temp (
                student_id, first_name, middle_name, last_name,
                mother_name, father_name, address, email,
                mobile_number, dob, class_name, whatsapp_no,
                gender, doa, roll_number, outstanding_balance, extra_balance)
                SELECT student_id, first_name, middle_name, last_name,
                mother_name, father_name, address, email,
                mobile_number, dob, class_name, whatsapp_no,
                gender, doa, roll_number, outstanding_balance, 0.0
                FROM students''')
            c.execute("DROP TABLE students")
            c.execute("ALTER TABLE students_temp RENAME TO students")
        
        # Ensure roll_number column exists
        c.execute("PRAGMA table_info(students)")
        columns = [col[1] for col in c.fetchall()]
        if 'roll_number' not in columns:
            c.execute("ALTER TABLE students ADD COLUMN roll_number TEXT")
        
        # Ensure outstanding_balance column exists
        if 'outstanding_balance' not in columns:
            c.execute("ALTER TABLE students ADD COLUMN outstanding_balance REAL DEFAULT 0.0")
        
        # Ensure extra_balance column exists
        if 'extra_balance' not in columns:
            c.execute("ALTER TABLE students ADD COLUMN extra_balance REAL DEFAULT 0.0")
        
        # Create payments table
        c.execute('''CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id TEXT NOT NULL,
            student_id TEXT,
            amount REAL NOT NULL,
            payment_date TEXT,
            FOREIGN KEY(student_id) REFERENCES students(student_id)
        )''')
        
        # Create results table
        c.execute('''CREATE TABLE IF NOT EXISTS results (
            student_id TEXT,
            subject TEXT NOT NULL,
            marks REAL NOT NULL,
            FOREIGN KEY(student_id) REFERENCES students(student_id)
        )''')
        
        # Create users table
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY NOT NULL,
            password TEXT NOT NULL
        )''')
        
        # Create report_cards table
        c.execute('''CREATE TABLE IF NOT EXISTS report_cards (
            report_id TEXT PRIMARY KEY,
            student_id TEXT,
            academic_year TEXT,
            pdf_data BLOB,
            generated_date TEXT,
            FOREIGN KEY(student_id) REFERENCES students(student_id)
        )''')
        
        # Create invoices table
        c.execute('''CREATE TABLE IF NOT EXISTS invoices (
            invoice_id TEXT PRIMARY KEY,
            student_id TEXT,
            school_fee REAL,
            bus_fee REAL,
            pdf_data BLOB,
            generated_date TEXT,
            FOREIGN KEY(student_id) REFERENCES students(student_id)
        )''')
        
        # Create receipts table
        c.execute('''CREATE TABLE IF NOT EXISTS receipts (
            receipt_id TEXT PRIMARY KEY,
            student_id TEXT,
            payment_id TEXT,
            pdf_data BLOB,
            generated_date TEXT,
            FOREIGN KEY(student_id) REFERENCES students(student_id),
            FOREIGN KEY(payment_id) REFERENCES payments(payment_id)
        )''')
        
        # Check if admin user exists, if not, create it
        c.execute("SELECT * FROM users WHERE username = ?", ('admin',))
        user = c.fetchone()
        if not user:
            hashed_password = hashlib.sha256('admin123'.encode()).hexdigest()
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                   ('admin', hashed_password))
        
        conn.commit()
    except sqlite3.OperationalError as e:
        print(f"Database error during initialization: {e}")
        raise
    except Exception as e:
        print(f"Error during database initialization: {e}")
        raise
    finally:
        if conn:
            conn.close()

# Generate next student ID in EPSXXXX format
def get_next_student_id():
    conn = None
    try:
        conn = sqlite3.connect('school.db', timeout=10)
        c = conn.cursor()
        c.execute("SELECT student_id FROM students WHERE student_id LIKE 'EPS%' ORDER BY student_id DESC LIMIT 1")
        last_id = c.fetchone()
        if last_id:
            last_number = int(last_id[0].replace('EPS', ''))
            next_number = last_number + 1
        else:
            next_number = 1001
        student_id = f'EPS{next_number:04d}'
        return student_id
    finally:
        if conn:
            conn.close()

# Verify login credentials
def verify_login(username, password):
    conn = None
    try:
        conn = sqlite3.connect('school.db', timeout=10)
        c = conn.cursor()
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, hashed_password))
        user = c.fetchone()
        return user is not None
    finally:
        if conn:
            conn.close()

# Add student to database
def add_student(data):
    conn = None
    try:
        conn = sqlite3.connect('school.db', timeout=10)
        c = conn.cursor()
        student_id = get_next_student_id()
        c.execute('''INSERT INTO students (student_id, first_name, middle_name, last_name, mother_name, father_name,
                   address, email, mobile_number, dob, class_name, whatsapp_no, gender, doa, roll_number, outstanding_balance, extra_balance)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 0.0)''',
                  (student_id, *data))
        conn.commit()
        return student_id
    finally:
        if conn:
            conn.close()

# Fetch all students
def get_all_students():
    conn = None
    try:
        conn = sqlite3.connect('school.db', timeout=10)
        df = pd.read_sql_query("SELECT * FROM students", conn)
        return df
    finally:
        if conn:
            conn.close()

# Fetch student by ID
def get_student(student_id):
    conn = None
    try:
        conn = sqlite3.connect('school.db', timeout=10)
        c = conn.cursor()
        c.execute("SELECT * FROM students WHERE student_id = ?", (student_id,))
        student = c.fetchone()
        return student
    finally:
        if conn:
            conn.close()

# Update student's outstanding and extra balances
def update_balances(c, student_id, new_outstanding, new_extra):
    c.execute("UPDATE students SET outstanding_balance = ?, extra_balance = ? WHERE student_id = ?",
              (new_outstanding, new_extra, student_id))

# Record payment
def record_payment(student_id, school_fee, bus_fee, amount):
    conn = None
    max_retries = 3
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect('school.db', timeout=10)
            c = conn.cursor()
            
            payment_id = f'PAY{str(uuid.uuid4())[:8]}'
            payment_date = datetime.now().strftime("%Y-%m-%d")
            
            c.execute("INSERT INTO payments (payment_id, student_id, amount, payment_date) VALUES (?, ?, ?, ?)",
                      (payment_id, student_id, amount, payment_date))
            
            total_due = school_fee + bus_fee
            
            c.execute("SELECT outstanding_balance, extra_balance FROM students WHERE student_id = ?", (student_id,))
            current_outstanding, current_extra = c.fetchone()
            current_outstanding = current_outstanding or 0.0
            current_extra = current_extra or 0.0
            
            effective_total_due = total_due - current_extra
            effective_total_due = max(0, effective_total_due)
            transaction_difference = amount - effective_total_due
            
            if transaction_difference < 0:
                new_outstanding = current_outstanding - transaction_difference
                new_extra = 0.0
                transaction_outstanding = -transaction_difference
                transaction_extra = 0.0
            else:
                new_outstanding = 0.0
                new_extra = transaction_difference
                transaction_outstanding = 0.0
                transaction_extra = transaction_difference if transaction_difference > 0 else 0.0
            
            update_balances(c, student_id, new_outstanding, new_extra)
            
            conn.commit()
            return (payment_id, payment_date, transaction_outstanding, transaction_extra, new_outstanding, new_extra)
        
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                print(f"Database is locked, retrying ({attempt + 1}/{max_retries})...")
                time.sleep(retry_delay)
                continue
            else:
                print(f"Database error in record_payment: {e}")
                raise
        except Exception as e:
            print(f"Error in record_payment: {e}")
            raise
        finally:
            if conn:
                conn.close()

# Save invoice to database
def save_invoice(student_id, school_fee, bus_fee, pdf_buffer, invoice_id):
    conn = None
    try:
        conn = sqlite3.connect('school.db', timeout=10)
        c = conn.cursor()
        generated_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pdf_data = pdf_buffer.getvalue()
        c.execute("INSERT INTO invoices (invoice_id, student_id, school_fee, bus_fee, pdf_data, generated_date) VALUES (?, ?, ?, ?, ?, ?)",
                  (invoice_id, student_id, school_fee, bus_fee, pdf_data, generated_date))
        conn.commit()
        return invoice_id
    finally:
        if conn:
            conn.close()

# Search invoices by student ID
def search_invoices(student_id):
    conn = None
    try:
        conn = sqlite3.connect('school.db', timeout=10)
        query = "SELECT invoice_id, student_id, school_fee, bus_fee, pdf_data, generated_date FROM invoices WHERE 1=1"
        params = []
        if student_id:
            query += " AND student_id = ?"
            params.append(student_id)
        query += " ORDER BY generated_date DESC"
        df = pd.read_sql_query(query, conn, params=params)
        return df
    finally:
        if conn:
            conn.close()

# Generate PDF invoice
def generate_invoice(student, school_fee, bus_fee, invoice_id):
    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=A5, topMargin=0.3*inch, bottomMargin=0.3*inch, leftMargin=0.3*inch, rightMargin=0.3*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    bold_center = ParagraphStyle(name='BoldCenter', fontSize=12, alignment=1, fontName='Helvetica-Bold', textColor=colors.black)
    subheader_center = ParagraphStyle(name='SubHeaderCenter', fontSize=8, alignment=1, fontName='Helvetica', textColor=colors.grey)
    normal_center = ParagraphStyle(name='NormalCenter', fontSize=8, alignment=1, fontName='Helvetica')
    normal_left = ParagraphStyle(name='NormalLeft', fontSize=8, alignment=0, fontName='Helvetica')
    
    header_data = [
        [
            [
                Paragraph("Evergreen Public School", bold_center),
                Spacer(1, 0.05*inch),
                Paragraph("Tirmohani, Nawada Persauni, Gopalganj, Bihar, Pin Code – 841440", subheader_center),
                Paragraph("Proprietor: Ansar Ali (Munna)", subheader_center),
            ]
        ]
    ]
    header_table = Table(header_data, colWidths=[A5[0] - 0.6*inch])
    header_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('BACKGROUND', (0, 0), (-1, -1), colors.lightgrey),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.1*inch))
    
    invoice_date = datetime.now().strftime("%Y-%m-%d")
    elements.append(Paragraph("Fee Invoice", ParagraphStyle(name='InvoiceTitle', fontSize=10, alignment=1, fontName='Helvetica-Bold')))
    elements.append(Spacer(1, 0.05*inch))
    invoice_details_data = [
        [Paragraph(f"<b>Invoice No:</b> {invoice_id}", normal_left),
         Paragraph(f"<b>Date:</b> {invoice_date}", normal_left)]
    ]
    invoice_details_table = Table(invoice_details_data, colWidths=[(A5[0] - 0.6*inch)/2, (A5[0] - 0.6*inch)/2])
    invoice_details_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]))
    elements.append(invoice_details_table)
    elements.append(Spacer(1, 0.1*inch))
    
    student_details_data = [
        [Paragraph(f"<b>Name:</b> {student[1]} {student[2] or ''} {student[3]}", normal_left),
         Paragraph(f"<b>Class:</b> {student[10]}", normal_left)],
        [Paragraph(f"<b>Student ID:</b> {student[0]}", normal_left),
         Paragraph(f"<b>Roll Number:</b> {student[14]}", normal_left)]
    ]
    student_details_table = Table(student_details_data, colWidths=[(A5[0] - 0.6*inch)/2, (A5[0] - 0.6*inch)/2])
    student_details_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    elements.append(student_details_table)
    elements.append(Spacer(1, 0.1*inch))
    
    outstanding_balance = student[15] or 0.0
    extra_balance = student[16] or 0.0
    subtotal = school_fee + bus_fee
    adjusted_total = subtotal + outstanding_balance - extra_balance
    adjusted_total = max(0, adjusted_total)
    
    fee_data = [
        ['S.No.', 'Description', 'Amount'],
        ['1', 'School Fee', f'₹{school_fee:.2f}'],
        ['2', 'Bus Fee', f'₹{bus_fee:.2f}'],
    ]
    row_count = 3
    if outstanding_balance > 0:
        fee_data.append([str(row_count), 'Previous Outstanding', f'₹{outstanding_balance:.2f}'])
        row_count += 1
    if extra_balance > 0:
        fee_data.append([str(row_count), 'Previous Extra (Deducted)', f'₹{extra_balance:.2f}'])
        row_count += 1
    fee_data.append(['', 'Total', f'₹{adjusted_total:.2f}'])
    
    fee_table = Table(fee_data, colWidths=[0.5*inch, (A5[0] - 1.3*inch), 1.2*inch])
    fee_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTNAME', (1, -1), (2, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (1, -1), (2, -1), colors.lightgrey),
        ('BACKGROUND', (1, 2), (2, 2), colors.yellow) if outstanding_balance > 0 else ('BACKGROUND', (0, 0), (0, 0), colors.white),
        ('BACKGROUND', (1, 3), (2, 3), colors.lightgreen) if extra_balance > 0 and outstanding_balance > 0 else 
        ('BACKGROUND', (1, 2), (2, 2), colors.lightgreen) if extra_balance > 0 else ('BACKGROUND', (0, 0), (0, 0), colors.white),
    ]))
    elements.append(fee_table)
    elements.append(Spacer(1, 0.2*inch))
    
    footer_data = [
        [Paragraph("________________________", normal_center)],
        [Paragraph("Authorized Signature", normal_center)],
        [Paragraph(f"Date: {invoice_date}", normal_center)]
    ]
    footer_table = Table(footer_data, colWidths=[A5[0] - 0.6*inch])
    footer_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]))
    elements.append(footer_table)
    
    pdf.build(elements)
    buffer.seek(0)
    return buffer

# Save receipt to database
def save_receipt(student_id, payment_id, pdf_buffer):
    conn = None
    try:
        conn = sqlite3.connect('school.db', timeout=10)
        c = conn.cursor()
        receipt_id = f'REC{str(uuid.uuid4())[:8]}'
        generated_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pdf_data = pdf_buffer.getvalue()
        c.execute("INSERT INTO receipts (receipt_id, student_id, payment_id, pdf_data, generated_date) VALUES (?, ?, ?, ?, ?)",
                  (receipt_id, student_id, payment_id, pdf_data, generated_date))
        conn.commit()
        return receipt_id
    finally:
        if conn:
            conn.close()

# Search receipts by student ID
def search_receipts(student_id):
    conn = None
    try:
        conn = sqlite3.connect('school.db', timeout=10)
        query = "SELECT receipt_id, student_id, payment_id, pdf_data, generated_date FROM receipts WHERE 1=1"
        params = []
        if student_id:
            query += " AND student_id = ?"
            params.append(student_id)
        query += " ORDER BY generated_date DESC"
        df = pd.read_sql_query(query, conn, params=params)
        return df
    finally:
        if conn:
            conn.close()

# Redesigned Payment Receipt with modern design
def generate_receipt(student, school_fee, bus_fee, amount, payment_id, payment_date, transaction_outstanding, transaction_extra, total_outstanding, total_extra):
    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=A5, topMargin=0.3*inch, bottomMargin=0.3*inch, leftMargin=0.3*inch, rightMargin=0.3*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Define modern styles
    bold_center = ParagraphStyle(name='BoldCenter', fontSize=12, alignment=1, fontName='Helvetica-Bold', textColor=colors.black)
    subheader_center = ParagraphStyle(name='SubHeaderCenter', fontSize=8, alignment=1, fontName='Helvetica', textColor=colors.grey)
    normal_center = ParagraphStyle(name='NormalCenter', fontSize=8, alignment=1, fontName='Helvetica')
    normal_left = ParagraphStyle(name='NormalLeft', fontSize=8, alignment=0, fontName='Helvetica')
    title_style = ParagraphStyle(name='Title', fontSize=14, alignment=1, fontName='Helvetica-Bold', textColor=colors.darkblue, spaceAfter=6)
    label_style = ParagraphStyle(name='Label', fontSize=8, fontName='Helvetica-Bold', alignment=0)
    
    # Modern Header
    header_data = [
        [
            Paragraph("[School Logo]", normal_center),  # Placeholder for logo
            [
                Paragraph("Evergreen Public School", bold_center),
                Spacer(1, 0.05*inch),
                Paragraph("Tirmohani, Nawada Persauni", subheader_center),
                Paragraph("Gopalganj, Bihar – 841440", subheader_center),
                Paragraph("Proprietor: Ansar Ali (Munna)", subheader_center),
            ]
        ]
    ]
    header_table = Table(header_data, colWidths=[1*inch, A5[0] - 1.6*inch])
    header_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('BACKGROUND', (0, 0), (-1, -1), colors.lightgrey),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.1*inch))
    
    # Receipt Title and Details
    elements.append(Paragraph("Payment Receipt", title_style))
    receipt_details_data = [
        [Paragraph(f"<b>Payment ID:</b> {payment_id}", normal_left),
         Paragraph(f"<b>Date:</b> {payment_date}", normal_left)]
    ]
    receipt_details_table = Table(receipt_details_data, colWidths=[(A5[0] - 0.6*inch)/2, (A5[0] - 0.6*inch)/2])
    receipt_details_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]))
    elements.append(receipt_details_table)
    elements.append(Spacer(1, 0.1*inch))
    
    # Student Information
    student_data = [
        [Paragraph(f"<b>Name:</b> {student[1]} {student[2] or ''} {student[3]}", normal_left),
         Paragraph(f"<b>Class:</b> {student[10]}", normal_left)],
        [Paragraph(f"<b>Student ID:</b> {student[0]}", normal_left),
         Paragraph(f"<b>Roll Number:</b> {student[14]}", normal_left)],
    ]
    student_table = Table(student_data, colWidths=[(A5[0] - 0.6*inch)/2, (A5[0] - 0.6*inch)/2])
    student_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    elements.append(student_table)
    elements.append(Spacer(1, 0.1*inch))
    
    # Fee Details Table
    total_due = school_fee + bus_fee
    previous_extra = student[16] or 0.0
    effective_total_due = max(0, total_due - previous_extra)
    payment_type = "Full Payment" if amount >= effective_total_due else "Partial Payment"
    
    data = [
        ['Description', 'Amount'],
        ['School Fee', f'₹{school_fee:.2f}'],
        ['Bus Fee', f'₹{bus_fee:.2f}'],
        ['Total Due', f'₹{total_due:.2f}'],
    ]
    row_count = 4
    if previous_extra > 0:
        data.append(['Previous Extra (Deducted)', f'₹{previous_extra:.2f}'])
        data.append(['Effective Total Due', f'₹{effective_total_due:.2f}'])
        row_count += 2
    data.extend([
        ['Amount Paid', f'₹{amount:.2f}'],
        ['Outstanding (This Transaction)', f'₹{transaction_outstanding:.2f}'],
    ])
    row_count += 2
    if transaction_extra > 0:
        data.append(['Extra Amount (This Transaction)', f'₹{transaction_extra:.2f}'])
        row_count += 1
    data.extend([
        ['Total Outstanding Balance', f'₹{total_outstanding:.2f}'],
        ['Total Extra Balance', f'₹{total_extra:.2f}'],
        ['Payment Type', payment_type]
    ])
    
    table = Table(data, colWidths=[3*inch, 1.5*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTNAME', (0, row_count-5), (0, row_count-1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 1), (-1, 1), colors.white),
        ('BACKGROUND', (0, 2), (-1, 2), colors.lightgrey),
        ('BACKGROUND', (0, 3), (-1, 3), colors.white),
        ('BACKGROUND', (0, row_count-5), (-1, row_count-5), colors.lightgreen if amount >= effective_total_due else colors.lightcoral),
        ('BACKGROUND', (0, row_count-4), (-1, row_count-4), colors.yellow if transaction_outstanding > 0 else colors.lightgrey),
        ('BACKGROUND', (0, row_count-3), (-1, row_count-3), colors.lightgreen) if transaction_extra > 0 else ('BACKGROUND', (0, 0), (0, 0), colors.white),
        ('BACKGROUND', (0, row_count-2), (-1, row_count-2), colors.yellow if total_outstanding > 0 else colors.lightgrey),
        ('BACKGROUND', (0, row_count-1), (-1, row_count-1), colors.lightgreen if total_extra > 0 else colors.lightgrey),
        ('BACKGROUND', (0, row_count), (-1, row_count), colors.lightblue),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.1*inch))
    
    # Divider Line
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    elements.append(Spacer(1, 0.05*inch))
    
    # Modern Footer
    footer_data = [
        [Paragraph(f"Date: {payment_date}", normal_left),
         Paragraph("Thank you for your payment!", normal_center),
         Paragraph("Authorized Signature: __________________", normal_left)]
    ]
    footer_table = Table(footer_data, colWidths=[1.5*inch, 1.5*inch, 2*inch])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]))
    elements.append(footer_table)
    
    pdf.build(elements)
    buffer.seek(0)
    return buffer

# Save report card to database
def save_report_card(student_id, academic_year, pdf_buffer):
    conn = None
    try:
        conn = sqlite3.connect('school.db', timeout=10)
        c = conn.cursor()
        report_id = f'REP{str(uuid.uuid4())[:8]}'
        generated_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pdf_data = pdf_buffer.getvalue()
        c.execute("INSERT INTO report_cards (report_id, student_id, academic_year, pdf_data, generated_date) VALUES (?, ?, ?, ?, ?)",
                  (report_id, student_id, academic_year, pdf_data, generated_date))
        conn.commit()
        return report_id
    finally:
        if conn:
            conn.close()

# Search report cards by student ID and academic year
def search_report_cards(student_id, academic_year):
    conn = None
    try:
        conn = sqlite3.connect('school.db', timeout=10)
        query = "SELECT report_id, student_id, academic_year, pdf_data, generated_date FROM report_cards WHERE 1=1"
        params = []
        if student_id:
            query += " AND student_id = ?"
            params.append(student_id)
        if academic_year:
            query += " AND academic_year = ?"
            params.append(academic_year)
        query += " ORDER BY generated_date DESC"
        df = pd.read_sql_query(query, conn, params=params)
        return df
    finally:
        if conn:
            conn.close()

# Generate PDF result card
def generate_result_card(student, results, academic_year="2024-2025", attendance_percentage=95):
    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=A5, topMargin=0.3*inch, bottomMargin=0.3*inch, leftMargin=0.5*inch, rightMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    header_style = ParagraphStyle(name='Header', fontSize=16, alignment=1, fontName='Helvetica-Bold', textColor=colors.darkblue)
    subheader_style = ParagraphStyle(name='SubHeader', fontSize=9, alignment=1, fontName='Helvetica', textColor=colors.grey)
    normal_center = ParagraphStyle(name='NormalCenter', fontSize=8, alignment=1)
    normal_center_bold = ParagraphStyle(name='NormalCenterBold', fontSize=8, alignment=1, fontName='Helvetica-Bold')
    normal_left = ParagraphStyle(name='NormalLeft', fontSize=8, alignment=0)
    small_left = ParagraphStyle(name='SmallLeft', fontSize=7, alignment=0)
    
    header_data = [
        [
            [
                Paragraph("Evergreen Public School", header_style),
                Spacer(1, 0.05*inch),
                Paragraph("Tirmohani, Nawada Persauni, Gopalganj, Bihar, Pin Code – 841440", subheader_style),
                Paragraph("Proprietor: Ansar Ali (Munna)", subheader_style),
                Spacer(1, 0.05*inch),
                Paragraph(f"Academic Year: {academic_year}", normal_center_bold),
            ]
        ]
    ]
    header_table = Table(header_data, colWidths=[A5[0] - 1*inch])
    header_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, -1), colors.lightgrey),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.1*inch))
    
    student_data = [
        [Paragraph(f"<b>Name:</b> {student[1]} {student[2] or ''} {student[3]}", normal_left),
         Paragraph(f"<b>Class:</b> {student[10]}", normal_left)],
        [Paragraph(f"<b>Student ID:</b> {student[0]}", normal_left),
         Paragraph(f"<b>Roll Number:</b> {student[14]}", normal_left)],
        [Paragraph(f"<b>Father's Name:</b> {student[5]}", normal_left),
         Paragraph(f"<b>Mother's Name:</b> {student[4]}", normal_left)],
        [Paragraph(f"<b>Date of Birth:</b> {student[9]}", normal_left),
         Paragraph(f"<b>Admission Date:</b> {student[13]}", normal_left)]
    ]
    student_table = Table(student_data, colWidths=[2.5*inch, 2.5*inch])
    student_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]))
    elements.append(student_table)
    elements.append(Spacer(1, 0.1*inch))
    
    max_marks_per_subject = 100
    passing_marks = 40
    data = [['S.No.', 'Subject', 'Marks', 'Max', 'Grade', 'Status']]
    total_marks = 0
    total_max_marks = 0
    for idx, result in enumerate(results, 1):
        marks = result[2]
        total_marks += marks
        total_max_marks += max_marks_per_subject
        if marks >= 90:
            subject_grade = "A+"
        elif marks >= 80:
            subject_grade = "A"
        elif marks >= 70:
            subject_grade = "B"
        elif marks >= 60:
            subject_grade = "C"
        elif marks >= 50:
            subject_grade = "D"
        elif marks >= 40:
            subject_grade = "E"
        else:
            subject_grade = "F"
        status = "Pass" if marks >= passing_marks else "Fail"
        row = [str(idx), result[1], f"{marks:.0f}", f"{max_marks_per_subject:.0f}", subject_grade, status]
        data.append(row)
    
    marks_table = Table(data, colWidths=[0.4*inch, 1.8*inch, 0.8*inch, 0.8*inch, 0.6*inch, 0.6*inch])
    marks_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    for i in range(1, len(data)):
        status = data[i][5]
        bg_color = colors.lightgreen if status == "Pass" else colors.lightcoral
        marks_table.setStyle(TableStyle([
            ('BACKGROUND', (0, i), (-1, i), bg_color),
        ]))
    elements.append(Paragraph("Academic Performance", styles['Heading4']))
    elements.append(Spacer(1, 0.05*inch))
    elements.append(marks_table)
    elements.append(Spacer(1, 0.1*inch))
    
    percentage = (total_marks / total_max_marks * 100) if total_max_marks > 0 else 0
    if percentage >= 90:
        overall_grade = "A+"
        remarks = "Outstanding! Keep up the excellent work."
    elif percentage >= 80:
        overall_grade = "A"
        remarks = "Excellent. Continue to strive for greatness."
    elif percentage >= 70:
        overall_grade = "B"
        remarks = "Good. Focus on consistency."
    elif percentage >= 60:
        overall_grade = "C"
        remarks = "Satisfactory. Work on weak areas."
    elif percentage >= 50:
        overall_grade = "D"
        remarks = "Needs improvement. Seek help."
    elif percentage >= 40:
        overall_grade = "E"
        remarks = "Below average. Extra effort needed."
    else:
        overall_grade = "F"
        remarks = "Unsatisfactory. Immediate attention needed."
    
    summary_data = [
        ['Total Marks', f"{total_marks:.0f}"],
        ['Max Marks', f"{total_max_marks:.0f}"],
        ['Percentage', f"{percentage:.1f}%"],
        ['Grade', overall_grade],
        ['Attendance', f"{attendance_percentage}%"],
        ['Remarks', remarks]
    ]
    summary_table = Table(summary_data, colWidths=[1.2*inch, 3.8*inch])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('BACKGROUND', (1, 3), (1, 3), colors.lightgreen if percentage >= 60 else colors.lightcoral),
        ('BACKGROUND', (1, 4), (1, 4), colors.lightgreen if attendance_percentage >= 75 else colors.yellow),
    ]))
    elements.append(Paragraph("Summary", styles['Heading4']))
    elements.append(Spacer(1, 0.05*inch))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.1*inch))
    
    footer_data = [
        [Paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d')}", small_left),
         Paragraph("School Stamp", normal_center),
         Paragraph("____________________", normal_center)],
        ['', '', Paragraph("Principal's Signature", normal_center)]
    ]
    footer_table = Table(footer_data, colWidths=[1.5*inch, 1.5*inch, 2*inch])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]))
    elements.append(footer_table)
    
    pdf.build(elements)
    buffer.seek(0)
    return buffer

# Main app with login
def main():
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        st.title("Evergreen Public School - Login")
        st.write("Tirmohani, Nawada Persauni, Gopalganj, Bihar, Pin Code – 841440")
        st.write("Proprietor: Ansar Ali (Munna)")
        
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            
            if submitted:
                if verify_login(username, password):
                    st.session_state.logged_in = True
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid username or password")
    else:
        st.title("Evergreen Public School Management System")
        st.write("Tirmohani, Nawada Persauni, Gopalganj, Bihar, Pin Code – 841440")
        st.write("Proprietor: Ansar Ali (Munna)")
        
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()
        
        menu = ["Student Admission", "Generate Invoice", "Record Payment", "Student Report", "Result Card", "Search Report Card"]
        choice = st.sidebar.selectbox("Select Option", menu)
        
        if choice == "Student Admission":
            st.subheader("Student Admission")
            with st.form("admission_form"):
                col1, col2 = st.columns(2)
                with col1:
                    first_name = st.text_input("First Name")
                    middle_name = st.text_input("Middle Name (Optional)", value="")
                    last_name = st.text_input("Last Name")
                    mother_name = st.text_input("Mother's Name")
                    father_name = st.text_input("Father's Name")
                    address = st.text_area("Address")
                with col2:
                    email = st.text_input("Email ID")
                    mobile_number = st.text_input("Mobile Number")
                    dob = st.date_input("Date of Birth")
                    class_name = st.selectbox("Class", ["Nursery", "LKG", "UKG", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"])
                    whatsapp_no = st.text_input("WhatsApp Number")
                    gender = st.selectbox("Gender", ["Male", "Female", "Other"])
                    doa = st.date_input("Date of Admission")
                    roll_number = st.text_input("Roll Number")
                submitted = st.form_submit_button("Submit")
                if submitted:
                    data = (first_name, middle_name, last_name, mother_name, father_name, address,
                            email, mobile_number, str(dob), class_name, whatsapp_no, gender, str(doa),
                            roll_number)
                    student_id = add_student(data)
                    st.success(f"Student {first_name} {last_name} added successfully! Student ID: {student_id}")
        
        elif choice == "Generate Invoice":
            st.subheader("Generate Invoice")
            action = st.selectbox("Select Action", ["Generate New Invoice", "Reprint Invoice"])
            
            if action == "Generate New Invoice":
                student_id = st.text_input("Enter Student ID")
                school_fee = st.number_input("School Fee", min_value=0.0, step=100.0)
                bus_fee = st.number_input("Bus Fee", min_value=0.0, step=100.0)
                student = get_student(student_id)
                if student:
                    outstanding_balance = student[15] or 0.0
                    extra_balance = student[16] or 0.0
                    subtotal = school_fee + bus_fee
                    adjusted_total = subtotal + outstanding_balance - extra_balance
                    adjusted_total = max(0, adjusted_total)
                    st.write(f"Previous Outstanding Balance: ₹{outstanding_balance:.2f}")
                    st.write(f"Previous Extra Balance: ₹{extra_balance:.2f}")
                    st.write(f"Total (After Adjustments): ₹{adjusted_total:.2f}")
                if st.button("Generate"):
                    if school_fee == 0 and bus_fee == 0 and (not student or (student[15] == 0 and student[16] == 0)):
                        st.error("Please enter at least one fee (School Fee or Bus Fee), or ensure there is an outstanding or extra balance.")
                    else:
                        if student:
                            invoice_id = f'INV{str(uuid.uuid4())[:8]}'
                            pdf_buffer = generate_invoice(student, school_fee, bus_fee, invoice_id)
                            save_invoice(student_id, school_fee, bus_fee, pdf_buffer, invoice_id)
                            st.download_button(
                                label="Download Invoice",
                                data=pdf_buffer,
                                file_name=f"invoice_{student[1]}_{student[3]}_{student[14]}.pdf",
                                mime="application/pdf"
                            )
                            st.success(f"Invoice generated and saved with ID: {invoice_id}")
                        else:
                            st.error("Student not found!")
            
            elif action == "Reprint Invoice":
                student_id = st.text_input("Enter Student ID to Search")
                if st.button("Search"):
                    invoices = search_invoices(student_id)
                    if not invoices.empty:
                        st.write("### Found Invoices")
                        for idx, row in invoices.iterrows():
                            col1, col2, col3 = st.columns([2, 2, 1])
                            with col1:
                                st.write(f"Student ID: {row['student_id']}")
                                st.write(f"School Fee: ₹{row['school_fee']:.2f}")
                            with col2:
                                st.write(f"Bus Fee: ₹{row['bus_fee']:.2f}")
                                st.write(f"Generated on: {row['generated_date']}")
                            with col3:
                                st.download_button(
                                    label="Download",
                                    data=row['pdf_data'],
                                    file_name=f"invoice_{row['student_id']}_{row['invoice_id']}.pdf",
                                    mime="application/pdf",
                                    key=f"download_invoice_{row['invoice_id']}"
                                )
                    else:
                        st.info("No invoices found for the given student ID.")
        
        elif choice == "Record Payment":
            st.subheader("Record Payment")
            action = st.selectbox("Select Action", ["Record New Payment", "Reprint Receipt"])
            
            if action == "Record New Payment":
                student_id = st.text_input("Enter Student ID")
                school_fee = st.number_input("School Fee", min_value=0.0, step=100.0, value=1200.0)
                bus_fee = st.number_input("Bus Fee", min_value=0.0, step=100.0, value=500.0)
                total = school_fee + bus_fee
                st.write(f"Total Due (This Transaction): ₹{total:.2f}")
                student = get_student(student_id)
                if student:
                    previous_extra = student[16] or 0.0
                    effective_total = max(0, total - previous_extra)
                    st.write(f"Previous Extra Balance: ₹{previous_extra:.2f}")
                    st.write(f"Effective Total Due: ₹{effective_total:.2f}")
                amount = st.number_input("Payment Amount", min_value=0.0, step=100.0)
                if st.button("Record Payment"):
                    if school_fee == 0 and bus_fee == 0:
                        st.error("Please enter at least one fee (School Fee or Bus Fee).")
                    elif amount <= 0:
                        st.error("Payment Amount must be greater than zero.")
                    else:
                        student = get_student(student_id)
                        if student:
                            try:
                                payment_id, payment_date, transaction_outstanding, transaction_extra, total_outstanding, total_extra = record_payment(student_id, school_fee, bus_fee, amount)
                                pdf_buffer = generate_receipt(student, school_fee, bus_fee, amount, payment_id, payment_date, transaction_outstanding, transaction_extra, total_outstanding, total_extra)
                                receipt_id = save_receipt(student_id, payment_id, pdf_buffer)
                                payment_type = "Full" if amount >= effective_total else "Partial"
                                st.download_button(
                                    label="Download Receipt",
                                    data=pdf_buffer,
                                    file_name=f"receipt_{student[1]}_{student[3]}_{student[14]}.pdf",
                                    mime="application/pdf"
                                )
                                st.success(f"{payment_type} Payment of ₹{amount:.2f} recorded successfully! Receipt ID: {receipt_id}, Total Outstanding: ₹{total_outstanding:.2f}, Total Extra: ₹{total_extra:.2f}")
                            except sqlite3.OperationalError as e:
                                st.error(f"Database error: {e}. Please try again.")
                        else:
                            st.error("Student not found!")
            
            elif action == "Reprint Receipt":
                student_id = st.text_input("Enter Student ID to Search")
                if st.button("Search"):
                    receipts = search_receipts(student_id)
                    if not receipts.empty:
                        st.write("### Found Receipts")
                        for idx, row in receipts.iterrows():
                            col1, col2, col3 = st.columns([2, 2, 1])
                            with col1:
                                st.write(f"Student ID: {row['student_id']}")
                                st.write(f"Payment ID: {row['payment_id']}")
                            with col2:
                                st.write(f"Generated on: {row['generated_date']}")
                                st.write(f"Receipt ID: {row['receipt_id']}")
                            with col3:
                                st.download_button(
                                    label="Download",
                                    data=row['pdf_data'],
                                    file_name=f"receipt_{row['student_id']}_{row['receipt_id']}.pdf",
                                    mime="application/pdf",
                                    key=f"download_receipt_{row['receipt_id']}"
                                )
                    else:
                        st.info("No receipts found for the given student ID.")
        
        elif choice == "Student Report":
            st.subheader("Student Report")
            df = get_all_students()
            if not df.empty:
                st.dataframe(df)
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download Report as CSV",
                    data=csv,
                    file_name="student_report.csv",
                    mime="text/csv"
                )
            else:
                st.info("No students found.")
        
        elif choice == "Result Card":
            st.subheader("Result Card")
            action = st.selectbox("Select Action", ["Generate New Result Card", "Reprint Result Card"])
            
            if action == "Generate New Result Card":
                student_id = st.text_input("Enter Student ID")
                attendance_percentage = st.number_input("Attendance Percentage", min_value=0.0, max_value=100.0, value=95.0, step=1.0)
                subjects = st.text_area("Enter Subjects and Marks (e.g., Math:80, Science:75)", placeholder="Math:80\nScience:75")
                if st.button("Generate"):
                    student = get_student(student_id)
                    if student:
                        results = []
                        for line in subjects.split('\n'):
                            if ':' in line:
                                try:
                                    subject, marks = line.split(':')
                                    marks = float(marks.strip())
                                    if marks < 0 or marks > 100:
                                        st.error(f"Marks for {subject} must be between 0 and 100.")
                                        break
                                    results.append((student_id, subject.strip(), marks))
                                except ValueError:
                                    st.error(f"Invalid format for marks in line: {line}. Use format 'Subject:Marks'.")
                                    break
                            else:
                                st.error(f"Invalid format in line: {line}. Use format 'Subject:Marks'.")
                                break
                        else:
                            if results:
                                academic_year = "2024-2025"
                                pdf_buffer = generate_result_card(student, results, academic_year, attendance_percentage)
                                report_id = save_report_card(student_id, academic_year, pdf_buffer)
                                st.success(f"Result card generated and saved with ID: {report_id}")
                                st.download_button(
                                    label="Download Result Card",
                                    data=pdf_buffer,
                                    file_name=f"result_{student[1]}_{student[3]}_{student[14]}_{academic_year}.pdf",
                                    mime="application/pdf"
                                )
                    else:
                        st.error("Student not found!")
            
            elif action == "Reprint Result Card":
                student_id = st.text_input("Enter Student ID to Search")
                academic_year = st.text_input("Academic Year (e.g., 2024-2025)", value="")
                if st.button("Search"):
                    report_cards = search_report_cards(student_id, academic_year if academic_year else None)
                    if not report_cards.empty:
                        st.write("### Found Result Cards")
                        for idx, row in report_cards.iterrows():
                            col1, col2, col3 = st.columns([2, 2, 1])
                            with col1:
                                st.write(f"Student ID: {row['student_id']}")
                                st.write(f"Academic Year: {row['academic_year']}")
                            with col2:
                                st.write(f"Generated on: {row['generated_date']}")
                                st.write(f"Report ID: {row['report_id']}")
                            with col3:
                                st.download_button(
                                    label="Download",
                                    data=row['pdf_data'],
                                    file_name=f"result_{row['student_id']}_{row['academic_year']}.pdf",
                                    mime="application/pdf",
                                    key=f"download_report_{row['report_id']}"
                                )
                    else:
                        st.info("No result cards found for the given criteria.")
        
        elif choice == "Search Report Card":
            st.subheader("Search Report Card")
            student_id = st.text_input("Enter Student ID to Search")
            academic_year = st.text_input("Academic Year (e.g., 2024-2025)", value="")
            if st.button("Search"):
                report_cards = search_report_cards(student_id, academic_year if academic_year else None)
                if not report_cards.empty:
                    st.write("### Found Result Cards")
                    for idx, row in report_cards.iterrows():
                        col1, col2, col3 = st.columns([2, 2, 1])
                        with col1:
                            st.write(f"Student ID: {row['student_id']}")
                            st.write(f"Academic Year: {row['academic_year']}")
                        with col2:
                            st.write(f"Generated on: {row['generated_date']}")
                            st.write(f"Report ID: {row['report_id']}")
                        with col3:
                            st.download_button(
                                label="Download",
                                data=row['pdf_data'],
                                file_name=f"result_{row['student_id']}_{row['academic_year']}.pdf",
                                mime="application/pdf",
                                key=f"download_search_{row['report_id']}"
                            )
                else:
                    st.info("No report cards found for the given criteria.")

if __name__ == "__main__":
    init_db()
    main()