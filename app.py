import os, sqlite3, hashlib, secrets, csv, io
from functools import wraps
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response

app = Flask(__name__)
# Set SECRET_KEY in Render's Environment settings. The fallback is for local development only.
app.secret_key = os.environ.get('SECRET_KEY') or 'local-development-only-change-this-secret'
DB = os.path.join(os.path.dirname(__file__), 'smartcampus.db')

def db():
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row; return conn

def pw_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 180000).hex()
    return f'{salt}${digest}'

def pw_ok(password, stored):
    try:
        salt = stored.split('$', 1)[0]
        return secrets.compare_digest(pw_hash(password, salt), stored)
    except Exception: return False

def init_db():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL, department TEXT DEFAULT 'CSE', roll TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS notices(id INTEGER PRIMARY KEY, title TEXT NOT NULL, message TEXT NOT NULL, category TEXT, author INTEGER, created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY, student INTEGER, subject TEXT, day TEXT, status TEXT, marked_by INTEGER, UNIQUE(student,subject,day));
        CREATE TABLE IF NOT EXISTS complaints(id INTEGER PRIMARY KEY, student INTEGER, title TEXT, description TEXT, category TEXT, status TEXT DEFAULT 'Open', created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS timetable(id INTEGER PRIMARY KEY, day TEXT, start TEXT, end TEXT, subject TEXT, room TEXT, department TEXT);
        ''')
        if c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
            demo = [('Campus Administrator','admin@smartcampus.local','Admin@123','admin','CSE',''),('Priya Verma','faculty@smartcampus.local','Faculty@123','faculty','CSE',''),('Aarav Sharma','student@smartcampus.local','Student@123','student','CSE','CSE2026001')]
            for n,e,p,r,d,roll in demo: c.execute('INSERT INTO users(name,email,password,role,department,roll) VALUES(?,?,?,?,?,?)',(n,e,pw_hash(p),r,d,roll))
            aid = c.execute("SELECT id FROM users WHERE role='admin'").fetchone()['id']
            c.execute('INSERT INTO notices(title,message,category,author) VALUES(?,?,?,?)',('Welcome to SmartCampus','The campus portal is now available for students and faculty.','General',aid))
            c.execute('INSERT INTO timetable(day,start,end,subject,room,department) VALUES(?,?,?,?,?,?)',('Monday','09:00','10:00','Data Structures','Lab 2','CSE'))
init_db()

def query(sql, args=()):
    with db() as c: return c.execute(sql,args).fetchall()
def execute(sql,args=()):
    with db() as c: cur=c.execute(sql,args); c.commit(); return cur.lastrowid
def current_user():
    if 'uid' not in session: return None
    rows=query('SELECT id,name,email,role,department,roll FROM users WHERE id=?',(session['uid'],))
    return rows[0] if rows else None
def login_required(fn):
    @wraps(fn)
    def wrapper(*a,**kw):
        if not current_user(): return redirect(url_for('login'))
        return fn(*a,**kw)
    return wrapper
def staff_required(fn):
    @wraps(fn)
    def wrapper(*a,**kw):
        u=current_user()
        if not u: return redirect(url_for('login'))
        if u['role'] not in ('admin','faculty'): flash('Faculty/admin access required.','error'); return redirect(url_for('dashboard'))
        return fn(*a,**kw)
    return wrapper

@app.context_processor
def inject_user(): return {'me':current_user(), 'today':date.today().isoformat()}

@app.route('/')
def home(): return redirect(url_for('dashboard') if current_user() else url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if current_user(): return redirect(url_for('dashboard'))
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        found=query('SELECT * FROM users WHERE lower(email)=?',(email,))
        if found and pw_ok(password,found[0]['password']): session['uid']=found[0]['id']; return redirect(url_for('dashboard'))
        flash('Incorrect email or password.','error')
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password',''); dept=request.form.get('department','CSE'); roll=request.form.get('roll','').strip()
    if not name or not email or len(password)<8: flash('Enter name, email and a password of at least 8 characters.','error')
    else:
        try: execute('INSERT INTO users(name,email,password,role,department,roll) VALUES(?,?,?,?,?,?)',(name,email,pw_hash(password),'student',dept,roll)); flash('Account created. Please sign in.','success')
        except sqlite3.IntegrityError: flash('That email is already registered.','error')
    return redirect(url_for('login'))

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    u=current_user(); students=query("SELECT COUNT(*) n FROM users WHERE role='student'")[0]['n']; faculty=query("SELECT COUNT(*) n FROM users WHERE role='faculty'")[0]['n']; notices_count=query('SELECT COUNT(*) n FROM notices')[0]['n']; open_complaints=query("SELECT COUNT(*) n FROM complaints WHERE status!='Resolved'")[0]['n']
    if u['role']=='student': att=query('SELECT COUNT(*) total, SUM(CASE WHEN status="Present" THEN 1 ELSE 0 END) present FROM attendance WHERE student=?',(u['id'],))[0]
    else: att=query('SELECT COUNT(*) total, SUM(CASE WHEN status="Present" THEN 1 ELSE 0 END) present FROM attendance')[0]
    pct=round((att['present'] or 0)*100/att['total'],1) if att['total'] else 0
    latest=query('SELECT n.*,u.name author_name FROM notices n LEFT JOIN users u ON u.id=n.author ORDER BY n.created DESC LIMIT 4')
    return render_template('dashboard.html', students=students,faculty=faculty,notices_count=notices_count,open_complaints=open_complaints,att=att,pct=pct,latest=latest)

@app.route('/students')
@login_required
@staff_required
def students():
    data=query("SELECT name,email,department,roll FROM users WHERE role='student' ORDER BY name")
    return render_template('students.html',students=data)

@app.route('/students/add',methods=['POST'])
@login_required
@staff_required
def add_student():
    if current_user()['role']!='admin': flash('Only administrators can add students.','error')
    else:
        n=request.form.get('name','').strip(); e=request.form.get('email','').strip().lower(); p=request.form.get('password',''); d=request.form.get('department','CSE'); r=request.form.get('roll','').strip()
        try:
            if not n or not e or len(p)<8: raise ValueError()
            execute('INSERT INTO users(name,email,password,role,department,roll) VALUES(?,?,?,?,?,?)',(n,e,pw_hash(p),'student',d,r)); flash('Student added.','success')
        except ValueError: flash('Fill all required fields; password must be 8+ characters.','error')
        except sqlite3.IntegrityError: flash('Email already exists.','error')
    return redirect(url_for('students'))

@app.route('/students.csv')
@login_required
@staff_required
def students_csv():
    data=query("SELECT name,email,department,roll FROM users WHERE role='student' ORDER BY name"); out=io.StringIO(); w=csv.writer(out); w.writerow(['Name','Email','Department','Roll Number'])
    for r in data: w.writerow([r['name'],r['email'],r['department'],r['roll']])
    return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=students.csv'})

@app.route('/notices',methods=['GET','POST'])
@login_required
def notices():
    u=current_user()
    if request.method=='POST' and u['role'] in ('admin','faculty'):
        title=request.form.get('title','').strip(); msg=request.form.get('message','').strip(); cat=request.form.get('category','General')
        if title and msg: execute('INSERT INTO notices(title,message,category,author) VALUES(?,?,?,?)',(title,msg,cat,u['id'])); flash('Notice published.','success')
        else: flash('Title and message are required.','error')
        return redirect(url_for('notices'))
    data=query('SELECT n.*,u.name author_name FROM notices n LEFT JOIN users u ON u.id=n.author ORDER BY n.created DESC')
    return render_template('notices.html',notices=data)

@app.route('/notices/<int:nid>/delete', methods=['POST'])
@login_required
def delete_notice(nid):
    # Only administrators may permanently delete campus notices.
    u=current_user()
    if u['role'] != 'admin':
        flash('Only administrators can delete notices.','error')
        return redirect(url_for('notices'))

    with db() as c:
        cur=c.execute('DELETE FROM notices WHERE id=?',(nid,))
        c.commit()
        deleted=cur.rowcount

    if deleted:
        flash('Notice deleted successfully.','success')
    else:
        flash('Notice was not found. It may already have been deleted.','error')
    return redirect(url_for('notices'))

@app.route('/attendance',methods=['GET','POST'])
@login_required
def attendance():
    u=current_user()
    if request.method=='POST' and u['role'] in ('admin','faculty'):
        student=request.form.get('student'); subject=request.form.get('subject','').strip(); day=request.form.get('day'); status=request.form.get('status')
        if student and subject and day and status in ('Present','Absent'):
            execute('INSERT INTO attendance(student,subject,day,status,marked_by) VALUES(?,?,?,?,?) ON CONFLICT(student,subject,day) DO UPDATE SET status=excluded.status,marked_by=excluded.marked_by',(student,subject,day,status,u['id'])); flash('Attendance saved.','success')
        else: flash('Complete all attendance fields.','error')
        return redirect(url_for('attendance'))
    students_list=query("SELECT id,name,roll FROM users WHERE role='student' ORDER BY name")
    if u['role']=='student': data=query('SELECT day,subject,status FROM attendance WHERE student=? ORDER BY day DESC',(u['id'],))
    else: data=query('SELECT a.day,u.name,a.subject,a.status FROM attendance a JOIN users u ON u.id=a.student ORDER BY a.day DESC')
    total=len(data); present=sum(1 for r in data if r['status']=='Present'); pct=round(present*100/total,1) if total else 0
    return render_template('attendance.html',records=data,students=students_list,pct=pct)

@app.route('/complaints',methods=['GET','POST'])
@login_required
def complaints():
    u=current_user()
    if request.method=='POST' and u['role']=='student':
        title=request.form.get('title','').strip(); desc=request.form.get('description','').strip(); cat=request.form.get('category','Other')
        if title and desc: execute('INSERT INTO complaints(student,title,description,category) VALUES(?,?,?,?)',(u['id'],title,desc,cat)); flash('Complaint submitted.','success')
        else: flash('Title and description are required.','error')
        return redirect(url_for('complaints'))
    if u['role']=='admin': data=query('SELECT c.*,u.name student_name FROM complaints c JOIN users u ON u.id=c.student ORDER BY c.created DESC')
    else: data=query('SELECT c.*,u.name student_name FROM complaints c JOIN users u ON u.id=c.student WHERE c.student=? ORDER BY c.created DESC',(u['id'],))
    return render_template('complaints.html',complaints=data)

@app.route('/complaints/<int:cid>/status',methods=['POST'])
@login_required
@staff_required
def complaint_status(cid):
    if current_user()['role']=='admin' and request.form.get('status') in ('Open','In Review','Resolved'): execute('UPDATE complaints SET status=? WHERE id=?',(request.form['status'],cid)); flash('Complaint status updated.','success')
    return redirect(url_for('complaints'))

@app.route('/timetable',methods=['GET','POST'])
@login_required
def timetable():
    u=current_user()
    if request.method=='POST' and u['role'] in ('admin','faculty'):
        vals=[request.form.get(k,'').strip() for k in ('day','start','end','subject','room','department')]
        if vals[3]: execute('INSERT INTO timetable(day,start,end,subject,room,department) VALUES(?,?,?,?,?,?)',vals); flash('Timetable entry added.','success')
        else: flash('Subject is required.','error')
        return redirect(url_for('timetable'))
    data=query("SELECT day,start,end,subject,room FROM timetable WHERE department=? ORDER BY CASE day WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 ELSE 6 END,start",(u['department'],))
    return render_template('timetable.html',entries=data)

if __name__ == '__main__': app.run(host='0.0.0.0',port=8000,debug=True)
