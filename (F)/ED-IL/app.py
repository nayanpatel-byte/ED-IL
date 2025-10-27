# app.py - Complete Modern Internship Portal
from flask import Flask, render_template, render_template_string, request, redirect, jsonify, session, url_for, send_from_directory, abort, flash
import json, os, datetime, threading
from werkzeug.utils import secure_filename

# Import admin blueprint
try:
    from admin_dashboard import admin_bp
except Exception:
    admin_bp = None

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production-very-secret-key')

# Register admin blueprint if available
if admin_bp:
    app.register_blueprint(admin_bp)

# Files & storage
BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, "data.json")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXT = {"pdf", "doc", "docx", "txt"}

# In-memory containers (will be loaded from disk)
students = []
internships = []
blogs = []

# --- Persistence helpers ---
def load_data():
    global students, internships, blogs
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            students = d.get("students", [])
            internships = d.get("internships", [])
            blogs = d.get("blogs", [])

            # Convert string skills to list
            for s in students:
                if isinstance(s.get("skills"), str):
                    s["skills"] = [x.strip() for x in s["skills"].split(",") if x.strip()]
            for it in internships:
                if isinstance(it.get("skills"), str):
                    it["skills"] = [x.strip() for x in it["skills"].split(",") if x.strip()]

        except Exception as e:
            print("Failed to load data.json:", e)
            students, internships, blogs = [], [], []
    else:
        students, internships, blogs = [], [], []


def save_data():
    tmp = DATA_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"students": students, "internships": internships, "blogs": blogs}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
    except Exception as e:
        print("Failed to save data.json:", e)

_save_lock = threading.Lock()
def schedule_save():
    with _save_lock:
        save_data()

# --- Helpers ---
def student_by_id(sid):
    try:
        sid = int(sid)
    except:
        return None
    for s in students:
        try:
            if int(s.get("id")) == sid:
                return s
        except:
            continue
    return None

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def all_known_skills():
    skills = set()
    for s in students:
        for sk in s.get("skills", []):
            skills.add(sk)
    for it in internships:
        for sk in it.get("skills", []):
            skills.add(sk)
    return sorted(skills)

def now_iso():
    return datetime.datetime.utcnow().isoformat()

def send_notification_to_student(sid, msg):
    st = student_by_id(sid)
    if not st:
        return False
    n = {"id": f"n{int(datetime.datetime.utcnow().timestamp()*1000)}", "msg": msg, "time": now_iso(), "read": False}
    st.setdefault("notifications", []).append(n)
    st["notifications_unread"] = st.get("notifications_unread", 0) + 1
    schedule_save()
    return True

def calculate_profile_completion(student):
    """Calculate profile completion percentage"""
    completion = 0
    if student.get('name'): completion += 25
    if student.get('education'): completion += 25
    if student.get('skills') and len(student.get('skills', [])) > 0: completion += 25
    if student.get('resume'): completion += 25
    return completion

def get_student_recommendations(student):
    """Get recommended internships for a student based on skills"""
    st_skills = set([s.lower() for s in student.get("skills", [])])
    recommendations = []
    
    for idx, it in enumerate(internships):
        it_skills = set([s.lower() for s in it.get("skills", [])])
        overlap = st_skills & it_skills
        
        if overlap:
            match_score = int((len(overlap) / len(it_skills)) * 100) if it_skills else 0
            recommendations.append({
                "iid": idx,
                "company": it.get("company"),
                "title": it.get("title"),
                "match_score": match_score,
                "matched_skills": list(overlap),
                "openings": it.get("openings", 1)
            })
    
    return sorted(recommendations, key=lambda x: x["match_score"], reverse=True)

# --- Template filter ---
@app.template_filter('intersect')
def intersect_filter(a, b):
    return list(set(a) & set(b))

# --- Context Processor ---
@app.context_processor
def inject_globals():
    """Inject global variables for all templates"""
    current_sid = session.get("current_student_id")
    current_student = student_by_id(current_sid) if current_sid else None
    
    unread_count = 0
    if current_student:
        unread_count = current_student.get("notifications_unread", 0)
    
    return {
        'current_user': current_student,
        'unread_notifications_count': unread_count
    }

# --- Routes ---
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    safe = os.path.basename(filename)
    path = os.path.join(UPLOAD_FOLDER, safe)
    if not os.path.exists(path):
        abort(404)
    return send_from_directory(UPLOAD_FOLDER, safe, as_attachment=True)

@app.route("/")
def home():
    """Show landing page first"""
    return render_template("landing.html")

@app.route("/student/login")
def student_login():
    return redirect(url_for("student_register"))

# --- Student Dashboard ---
@app.route("/student/dashboard")
def student_dashboard():
    """Modern student dashboard"""
    current_sid = session.get("current_student_id")
    if not current_sid:
        flash('Please login to access your dashboard', 'warning')
        return redirect(url_for('internship_listings'))
    
    student = student_by_id(current_sid)
    if not student:
        flash('Student not found', 'error')
        return redirect(url_for('internship_listings'))
    
    # Calculate statistics
    applications_count = sum(1 for it in internships if student['id'] in it.get('app_ids', []))
    accepted_count = sum(1 for it in internships if student['id'] in it.get('selected_ids', []))
    pending_count = applications_count - accepted_count
    profile_completion = calculate_profile_completion(student)
    
    # Get student's applications
    my_applications = []
    for it in internships:
        if student['id'] in it.get('app_ids', []):
            status = 'Accepted' if student['id'] in it.get('selected_ids', []) else 'Pending'
            my_applications.append({
                'company': it['company'],
                'position': it['title'],
                'applied_date': it.get('created_at', '')[:10] if it.get('created_at') else 'N/A',
                'status': status
            })
    
    # Get recommendations
    recommended_internships = get_student_recommendations(student)[:3]
    
    return render_template('student_dashboard.html',
                         student=student,
                         applications_count=applications_count,
                         accepted_count=accepted_count,
                         pending_count=pending_count,
                         profile_completion=profile_completion,
                         my_applications=my_applications,
                         recommended_internships=recommended_internships)

# --- Internship Listings ---
@app.route("/internships")
def internship_listings():
    """Modern internship listings page with search and filter functionality"""
    # Get search and filter parameters
    search_query = request.args.get('search', '').strip().lower()
    skill_filter = request.args.get('skill', '').strip().lower()
    location_filter = request.args.get('location', '').strip().lower()
    duration_filter = request.args.get('duration', '').strip().lower()
    sort_by = request.args.get('sort', 'recent')
    
    # Filter internships based on search query
    filtered_internships = []
    for idx, internship in enumerate(internships):
        # Check if search query matches title, company, or skills
        matches_search = True
        if search_query:
            title_match = search_query in internship.get('title', '').lower()
            company_match = search_query in internship.get('company', '').lower()
            skills_match = any(search_query in skill.lower() for skill in internship.get('skills', []))
            matches_search = title_match or company_match or skills_match
        
        # Check if skill filter matches
        matches_skill = True
        if skill_filter:
            matches_skill = any(skill_filter in skill.lower() for skill in internship.get('skills', []))
        
        # Check if location filter matches
        matches_location = True
        if location_filter:
            location = internship.get('location', '').lower()
            if location_filter == 'remote':
                matches_location = 'remote' in location
            elif location_filter == 'onsite':
                matches_location = 'onsite' in location or 'on-site' in location
            elif location_filter == 'hybrid':
                matches_location = 'hybrid' in location
        
        # Check if duration filter matches
        matches_duration = True
        if duration_filter:
            duration = internship.get('duration', '').lower()
            if duration_filter == '1-3':
                matches_duration = '1' in duration or '2' in duration or '3' in duration
            elif duration_filter == '3-6':
                matches_duration = '3' in duration or '4' in duration or '5' in duration or '6' in duration
            elif duration_filter == '6+':
                matches_duration = any(month in duration for month in ['7', '8', '9', '10', '11', '12', 'year'])
        
        if matches_search and matches_skill and matches_location and matches_duration:
            # Add index for reference
            internship_with_index = dict(internship)
            internship_with_index['index'] = idx
            filtered_internships.append(internship_with_index)
    
    # Sort internships
    if sort_by == 'recent':
        filtered_internships.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    elif sort_by == 'company':
        filtered_internships.sort(key=lambda x: x.get('company', ''))
    elif sort_by == 'title':
        filtered_internships.sort(key=lambda x: x.get('title', ''))
    
    return render_template('internship_listings.html', 
                          internships=filtered_internships,
                          search_query=search_query,
                          skill_filter=skill_filter,
                          location_filter=location_filter,
                          duration_filter=duration_filter,
                          sort_by=sort_by)

# --- Notifications ---
@app.route("/notifications")  
def notifications_page():
    """Modern notifications page"""
    current_sid = session.get("current_student_id")
    if not current_sid:
        flash('Please login to view notifications', 'warning')
        return redirect(url_for('internship_listings'))
    
    current_student = student_by_id(current_sid)
    if not current_student:
        return redirect(url_for('internship_listings'))
    
    return render_template('notifications.html', student=current_student)

# --- User Profile ---
@app.route("/profile")
def user_profile():
    """Modern user profile page"""
    current_sid = session.get("current_student_id")
    if not current_sid:
        flash('Please login to view your profile', 'warning')
        return redirect(url_for('internship_listings'))
    
    current_student = student_by_id(current_sid)
    if not current_student:
        return redirect(url_for('internship_listings'))
    
    # Calculate stats
    applications_count = sum(1 for it in internships if current_student['id'] in it.get('app_ids', []))
    selected_count = sum(1 for it in internships if current_student['id'] in it.get('selected_ids', []))
    
    return render_template('user_profile.html',
                         student=current_student,
                         applications_count=applications_count,
                         selected_count=selected_count)

@app.route("/profile/edit", methods=["POST"])
def profile_edit():
    """Handle profile updates"""
    current_sid = session.get("current_student_id")
    if not current_sid:
        return jsonify({"ok": False}), 401
    
    student = student_by_id(current_sid)
    if not student:
        return jsonify({"ok": False}), 404
    
    # Update fields
    if 'firstName' in request.form and 'lastName' in request.form:
        student['name'] = f"{request.form['firstName']} {request.form['lastName']}"
    if 'email' in request.form:
        student['email'] = request.form['email'].strip()
    if 'education' in request.form:
        student['education'] = request.form['education'].strip()
    
    # Handle resume upload
    if 'resume' in request.files:
        f = request.files['resume']
        if f and f.filename and allowed_file(f.filename):
            fname = f"{current_sid}_" + secure_filename(f.filename)
            save_path = os.path.join(UPLOAD_FOLDER, fname)
            f.save(save_path)
            student['resume'] = fname
    
    schedule_save()
    flash('Profile updated successfully!', 'success')
    return redirect(url_for('user_profile'))

# --- Student Register ---
@app.route("/student/register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        education = request.form.get("education", "").strip()
        email = request.form.get("email", "").strip()
        skills = request.form.get("skills", "").strip()
        skills = [s.strip() for s in skills.split(",") if s.strip()]
        
        # Generate new student ID
        sid = (max([int(s.get("id", 0)) for s in students]) + 1) if students else 1

        resume_filename = None
        if 'resume' in request.files:
            f = request.files['resume']
            if f and f.filename and allowed_file(f.filename):
                fname = f"{sid}_" + secure_filename(f.filename)
                save_path = os.path.join(UPLOAD_FOLDER, fname)
                f.save(save_path)
                resume_filename = fname

        student_obj = {
            "id": sid,
            "name": name,
            "email": email,
            "education": education,
            "skills": skills,
            "resume": resume_filename,
            "notifications": [],
            "notifications_unread": 0,
            "registered_at": now_iso()
        }
        students.append(student_obj)
        schedule_save()
        session['current_student_id'] = sid
        flash(f'Welcome {name}! Your registration is successful.', 'success')
        return redirect(url_for('student_dashboard'))
    
    return render_template('student_register.html')

# --- Company Register ---
@app.route("/company/register", methods=["GET", "POST"])
def company_register():
    if request.method == "POST":
        cname = request.form.get("name", "").strip()
        title = request.form.get("title", "").strip()
        skills_raw = request.form.get("skills", "").strip()
        skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
        
        try:
            openings = int(request.form.get("openings", "1"))
            if openings < 1:
                openings = 1
        except:
            openings = 1

        internships.insert(0, {
            "company": cname,
            "title": title,
            "skills": skills,
            "openings": openings,
            "apps": [],
            "app_ids": [],
            "selected_ids": [],
            "created_at": now_iso()
        })
        schedule_save()
        flash('Internship posted successfully!', 'success')
        return redirect(url_for('internship_listings'))
    
    return render_template('company_register.html')

# --- Apply Endpoints ---
@app.route("/apply", methods=["POST"])
def apply_form():
    try:
        sid = int(request.form.get("sid", ""))
        iid = int(request.form.get("iid", ""))
    except:
        return redirect(url_for('internship_listings'))
    
    s = student_by_id(sid)
    if s and 0 <= iid < len(internships):
        it = internships[iid]
        it.setdefault("app_ids", [])
        if s["id"] not in it["app_ids"]:
            it.setdefault("apps", []).append(s)
            it["app_ids"].append(s["id"])
            schedule_save()
            flash(f'Successfully applied to {it["title"]} at {it["company"]}!', 'success')
    
    return redirect(url_for('internship_listings'))

@app.route("/apply_ajax", methods=["POST"])
def apply_ajax():
    data = request.get_json() or {}
    try:
        iid = int(data.get("iid"))
    except:
        return jsonify({"status":"error", "message":"invalid internship id"}), 400

    if 'current_student_id' not in session:
        return jsonify({"status":"not_logged_in"}), 200

    s = student_by_id(session.get('current_student_id'))
    if not s:
        return jsonify({"status":"not_logged_in"}), 200

    if iid < 0 or iid >= len(internships):
        return jsonify({"status":"error", "message":"internship not found"}), 404

    it = internships[iid]
    it.setdefault('app_ids', [])
    
    if s["id"] in it['app_ids']:
        return jsonify({"status":"already", "message":"already applied"}), 200

    it.setdefault('apps', []).append(s)
    it['app_ids'].append(s["id"])
    schedule_save()
    
    # Send notification to student
    send_notification_to_student(s["id"], f"Your application for '{it['title']}' at {it['company']} has been submitted successfully.")
    
    return jsonify({"status":"ok", "message":"applied"}), 200

# --- Login/Logout Endpoints ---
@app.route("/login_student", methods=["POST"])
def login_student():
    data = request.get_json() or {}
    try:
        sid = int(data.get("sid"))
    except:
        return jsonify({"ok": False}), 400
    
    if student_by_id(sid):
        session['current_student_id'] = sid
        return jsonify({"ok": True})
    
    return jsonify({"ok": False}), 404

@app.route("/logout_student", methods=["POST"])
def logout_student():
    session.pop('current_student_id', None)
    flash('You have been logged out successfully.', 'success')
    return jsonify({"ok": True})

# --- Allocation ---
@app.route("/allocate/<int:iid>", methods=["GET", "POST"])
def allocate(iid):
    if iid < 0 or iid >= len(internships):
        flash('Internship not found', 'error')
        return redirect(url_for('internship_listings'))

    it = internships[iid]
    req_skills = set(it.get("skills", []))
    scored = sorted(it.get("apps", []), key=lambda s: len(req_skills & set(s.get("skills", []))), reverse=True)
    selected = scored[:it.get("openings", 1)]
    rejected = scored[it.get("openings", 1):]

    # Persist selection
    it['selected_ids'] = [int(s['id']) for s in selected]
    it['selected_ids'] = list(dict.fromkeys(it.get('selected_ids', [])))

    # Send notifications
    for s in selected:
        send_notification_to_student(s["id"], f"Congratulations! You have been ACCEPTED for '{it['title']}' at {it['company']}.")
    
    for s in rejected:
        send_notification_to_student(s["id"], f"Thank you for your interest in '{it['title']}' at {it['company']}. Unfortunately, you were not selected this time.")

    schedule_save()

    if request.method == "POST":
        feedback_data = request.form.get("feedback", "").strip()
        student_name = request.form.get("student_name")
        if feedback_data and student_name:
            it.setdefault("feedbacks", []).append({"student": student_name, "feedback": feedback_data, "time": now_iso()})
            schedule_save()
            flash('Feedback submitted successfully', 'success')
        return redirect(url_for("allocate", iid=iid))

    total_selected = len(selected)
    total_rejected = len(rejected)
    total_applied = len(it.get('apps', []))
    total_not_applied = max(total_applied - total_selected - total_rejected, 0)

    return render_template_string("""
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Allocation Results</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
</head>
<body class="bg-light">
<div class="container py-4">
  <div class="d-flex justify-content-between align-items-center mb-4">
    <h3>Allocation Results for "{{ it['title'] }}"</h3>
    <a href="{{ url_for('internship_listings') }}" class="btn btn-outline-primary">
      <i class="bi bi-arrow-left me-2"></i>Back
    </a>
  </div>
  
  <div class="row">
    <div class="col-md-6 mb-4">
      <div class="card">
        <div class="card-body">
          <h5 class="card-title">Distribution Chart</h5>
          <canvas id="allocationChart"></canvas>
        </div>
      </div>
    </div>
    
    <div class="col-md-6 mb-4">
      <div class="card">
        <div class="card-body">
          <h5 class="card-title mb-3">Selected Students ({{ total_selected }})</h5>
          {% if selected %}
            <ul class="list-group">
              {% for s in selected %}
                <li class="list-group-item d-flex justify-content-between align-items-center">
                  <div>
                    <strong>{{ s['name'] }}</strong>
                    <br><small class="text-muted">{{ s['skills']|join(', ') }}</small>
                  </div>
                  <span class="badge bg-success rounded-pill">Selected</span>
                </li>
              {% endfor %}
            </ul>
          {% else %}
            <p class="text-muted">No students selected yet.</p>
          {% endif %}
        </div>
      </div>
    </div>
  </div>

  <div class="row">
    <div class="col-12">
      <div class="card">
        <div class="card-body">
          <h5 class="card-title mb-3">Rejected Students ({{ total_rejected }})</h5>
          {% if rejected %}
            <div class="accordion" id="rejectedAccordion">
              {% for s in rejected %}
                <div class="accordion-item">
                  <h2 class="accordion-header" id="heading{{ loop.index }}">
                    <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" 
                            data-bs-target="#collapse{{ loop.index }}">
                      {{ s['name'] }} - {{ s.get('education', 'N/A') }}
                    </button>
                  </h2>
                  <div id="collapse{{ loop.index }}" class="accordion-collapse collapse" 
                       data-bs-parent="#rejectedAccordion">
                    <div class="accordion-body">
                      <p><strong>Skills:</strong> {{ s['skills']|join(', ') }}</p>
                      <form method="post" class="mt-3">
                        <input type="hidden" name="student_name" value="{{ s['name'] }}">
                        <div class="mb-3">
                          <label class="form-label">Provide Feedback</label>
                          <textarea name="feedback" class="form-control" rows="3" 
                                    placeholder="Share constructive feedback to help the student improve..." required></textarea>
                        </div>
                        <button class="btn btn-primary btn-sm">
                          <i class="bi bi-send me-2"></i>Submit Feedback
                        </button>
                      </form>
                    </div>
                  </div>
                </div>
              {% endfor %}
            </div>
          {% else %}
            <p class="text-muted">No rejected students.</p>
          {% endif %}
        </div>
      </div>
    </div>
  </div>

  {% if it.get("feedbacks") %}
    <div class="row mt-4">
      <div class="col-12">
        <div class="card">
          <div class="card-body">
            <h5 class="card-title mb-3">Submitted Feedbacks</h5>
            <ul class="list-group">
              {% for fb in it['feedbacks'] %}
                <li class="list-group-item">
                  <strong>{{ fb['student'] }}</strong>
                  <p class="mb-1 mt-2">{{ fb['feedback'] }}</p>
                  <small class="text-muted">{{ fb.get('time', '')[:10] }}</small>
                </li>
              {% endfor %}
            </ul>
          </div>
        </div>
      </div>
    </div>
  {% endif %}
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<script>
var ctx = document.getElementById('allocationChart').getContext('2d');
new Chart(ctx, {
    type: 'doughnut',
    data: {
        labels: ['Selected', 'Rejected', 'Not Applied'],
        datasets: [{
            data: [{{ total_selected }}, {{ total_rejected }}, {{ total_not_applied }}],
            backgroundColor: ['#198754','#dc3545','#6c757d']
        }]
    },
    options: { 
        responsive: true,
        plugins: {
            legend: {
                position: 'bottom'
            }
        }
    }
});
</script>
</body>
</html>
""", it=it, selected=selected, rejected=rejected, total_selected=total_selected, 
     total_rejected=total_rejected, total_not_applied=total_not_applied)

# --- Students / Companies Listing ---
@app.route("/students")
def list_students():
    return render_template_string("""
<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Students</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
</head>
<body class="bg-light p-4">
  <div class="container">
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h3>All Students</h3>
      <a href="{{ url_for('internship_listings') }}" class="btn btn-outline-primary">
        <i class="bi bi-arrow-left me-2"></i>Back
      </a>
    </div>
    
    <div class="card">
      <div class="card-body">
        <div class="table-responsive">
          <table class="table table-hover">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Email</th>
                <th>Education</th>
                <th>Skills</th>
                <th>Resume</th>
              </tr>
            </thead>
            <tbody>
            {% for s in students %}
              <tr>
                <td>{{ s['id'] }}</td>
                <td>{{ s['name'] }}</td>
                <td>{{ s.get('email', 'N/A') }}</td>
                <td>{{ s.get('education','N/A') }}</td>
                <td>
                  {% for skill in s.get('skills', [])[:3] %}
                    <span class="badge bg-primary me-1">{{ skill }}</span>
                  {% endfor %}
                  {% if s.get('skills')|length > 3 %}
                    <span class="badge bg-secondary">+{{ s.get('skills')|length - 3 }}</span>
                  {% endif %}
                </td>
                <td>
                  {% if s.get('resume') %}
                    <a href="/uploads/{{ s.get('resume') }}" target="_blank" class="btn btn-sm btn-outline-primary">
                      <i class="bi bi-download"></i>
                    </a>
                  {% else %}
                    <span class="text-muted">-</span>
                  {% endif %}
                </td>
              </tr>
            {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</body></html>
""", students=students)

@app.route("/companies")
def companies_list():
    return render_template_string("""
<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Companies</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
</head>
<body class="bg-light p-4">
  <div class="container">
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h3>Companies & Internships</h3>
      <div>
        <a href="{{ url_for('company_register') }}" class="btn btn-primary me-2">
          <i class="bi bi-plus-circle me-2"></i>Add Internship
        </a>
        <a href="{{ url_for('internship_listings') }}" class="btn btn-outline-primary">
          <i class="bi bi-arrow-left me-2"></i>Back
        </a>
      </div>
    </div>
    
    <div class="row">
      {% for it in internships %}
        <div class="col-md-6 mb-4">
          <div class="card h-100">
            <div class="card-body">
              <h5 class="card-title">{{ it['company'] }}</h5>
              <h6 class="card-subtitle mb-3 text-muted">{{ it['title'] }}</h6>
              <p><strong>Skills Required:</strong></p>
              <div class="mb-3">
                {% for skill in it['skills'] %}
                  <span class="badge bg-light text-dark me-1">{{ skill }}</span>
                {% endfor %}
              </div>
              <div class="row text-center">
                <div class="col-4">
                  <strong>{{ it.get('openings', 1) }}</strong>
                  <p class="small text-muted mb-0">Openings</p>
                </div>
                <div class="col-4">
                  <strong>{{ it.get('apps')|length }}</strong>
                  <p class="small text-muted mb-0">Applicants</p>
                </div>
                <div class="col-4">
                  <strong>{{ it.get('selected_ids', [])|length }}</strong>
                  <p class="small text-muted mb-0">Selected</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      {% endfor %}
    </div>
  </div>
</body></html>
""", internships=internships)

# --- Blog Routes ---
@app.route("/blog")
def blog_list():
    return render_template_string("""
<!doctype html><html><head><meta charset="utf-8"><title>Blog</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
</head>
<body class="bg-light p-4">
  <div class="container">
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h3>Blog</h3>
      <div>
        <a href="/blog/new" class="btn btn-primary me-2">
          <i class="bi bi-plus-circle me-2"></i>New Post
        </a>
        <a href="{{ url_for('internship_listings') }}" class="btn btn-outline-primary">
          <i class="bi bi-arrow-left me-2"></i>Back
        </a>
      </div>
    </div>
    
    <div class="row">
      {% for b in blogs %}
        <div class="col-md-6 mb-4">
          <div class="card h-100">
            <div class="card-body">
              <h5 class="card-title">{{ b['title'] }}</h5>
              <p class="card-text text-muted small mb-3">
                By {{ b.get('author','Unknown') }} on {{ b.get('time','')[:10] }}
              </p>
              <p class="card-text">{{ b['body'][:200] }}{% if b['body']|length > 200 %}...{% endif %}</p>
              <a href="/blog/view/{{ loop.index0 }}" class="btn btn-sm btn-outline-primary">
                Read More <i class="bi bi-arrow-right ms-1"></i>
              </a>
            </div>
          </div>
        </div>
      {% else %}
        <div class="col-12">
          <div class="alert alert-info">No blog posts yet. Be the first to create one!</div>
        </div>
      {% endfor %}
    </div>
  </div>
</body></html>
""", blogs=blogs)

@app.route("/blog/new", methods=["GET","POST"])
def blog_new():
    if request.method == "POST":
        title = request.form.get("title","Untitled").strip()
        body = request.form.get("body","").strip()
        author = request.form.get("author","Anonymous").strip()
        
        blogs.insert(0, {
            "title": title,
            "body": body,
            "author": author,
            "time": now_iso()
        })
        schedule_save()
        flash('Blog post published successfully!', 'success')
        return redirect("/blog")
    
    return render_template_string("""
<!doctype html><html><head><meta charset="utf-8"><title>New Blog Post</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet"></head>
<body class="bg-light p-4">
  <div class="container">
    <div class="card">
      <div class="card-body">
        <h3 class="card-title mb-4">Create New Blog Post</h3>
        <form method="post">
          <div class="mb-3">
            <label class="form-label">Title</label>
            <input name="title" class="form-control" placeholder="Enter post title" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Author</label>
            <input name="author" class="form-control" placeholder="Your name" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Content</label>
            <textarea name="body" rows="10" class="form-control" placeholder="Write your post..." required></textarea>
          </div>
          <button class="btn btn-primary">Publish</button>
          <a href="/blog" class="btn btn-outline-secondary">Cancel</a>
        </form>
      </div>
    </div>
  </div>
</body></html>
""")

@app.route("/blog/view/<int:bid>")
def blog_view(bid):
    if bid < 0 or bid >= len(blogs):
        flash('Blog post not found', 'error')
        return redirect("/blog")
    
    b = blogs[bid]
    return render_template_string("""
<!doctype html><html><head><meta charset="utf-8"><title>{{ b['title'] }}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
</head>
<body class="bg-light p-4">
  <div class="container">
    <div class="card">
      <div class="card-body">
        <h2 class="card-title">{{ b['title'] }}</h2>
        <p class="text-muted mb-4">By {{ b.get('author','Unknown') }} on {{ b.get('time','')[:10] }}</p>
        <div class="blog-content" style="white-space: pre-wrap;">{{ b['body'] }}</div>
        <hr class="my-4">
        <a href="/blog" class="btn btn-outline-primary">
          <i class="bi bi-arrow-left me-2"></i>Back to Blog
        </a>
      </div>
    </div>
  </div>
</body></html>
""", b=b)

# --- Skill Suggestions ---
@app.route("/skill_suggest")
def skill_suggest():
    q = (request.args.get("q") or "").strip().lower()
    if not q:
        return jsonify({"suggestions": []})
    
    all_sk = all_known_skills()
    suggestions = [s for s in all_sk if q in s.lower()][:25]
    return jsonify({"suggestions": suggestions})

# --- Notifications API ---
@app.route("/api/notifications/list")
def api_notifications_list():
    sid = session.get('current_student_id')
    if not sid:
        return jsonify({"notifications": []})
    
    st = student_by_id(sid)
    if not st:
        return jsonify({"notifications": []})
    
    notifs = list(reversed(st.get("notifications", [])))
    return jsonify({"notifications": notifs})

@app.route("/api/notifications/unread_count")
def api_notifications_unread_count():
    sid = session.get('current_student_id')
    if not sid:
        return jsonify({"unread": 0})
    
    st = student_by_id(sid)
    if not st:
        return jsonify({"unread": 0})
    
    return jsonify({"unread": st.get("notifications_unread", 0)})

@app.route("/api/notifications/toggle_read", methods=["POST"])
def api_notifications_toggle_read():
    data = request.get_json() or {}
    nid = data.get("id")
    sid = session.get('current_student_id')
    
    if not sid or not nid:
        return jsonify({"ok": False}), 400
    
    st = student_by_id(sid)
    if not st:
        return jsonify({"ok": False}), 404
    
    found = None
    for n in st.get("notifications", []):
        if n.get("id") == nid:
            found = n
            break
    
    if not found:
        return jsonify({"ok": False}), 404
    
    found["read"] = not bool(found.get("read"))
    st["notifications_unread"] = sum(1 for x in st.get("notifications", []) if not x.get("read"))
    schedule_save()
    
    return jsonify({"ok": True})

@app.route("/api/notifications/delete", methods=["POST"])
def api_notifications_delete():
    data = request.get_json() or {}
    nid = data.get("id")
    sid = session.get('current_student_id')
    
    if not sid or not nid:
        return jsonify({"ok": False}), 400
    
    st = student_by_id(sid)
    if not st:
        return jsonify({"ok": False}), 404
    
    st["notifications"] = [n for n in st.get("notifications", []) if n.get("id") != nid]
    st["notifications_unread"] = sum(1 for x in st.get("notifications", []) if not x.get("read"))
    schedule_save()
    
    return jsonify({"ok": True})

@app.route("/api/notifications/mark_all", methods=["POST"])
def api_notifications_mark_all():
    sid = session.get('current_student_id')
    if not sid:
        return jsonify({"ok": False}), 400
    
    st = student_by_id(sid)
    if not st:
        return jsonify({"ok": False}), 404
    
    for n in st.get("notifications", []):
        n["read"] = True
    st["notifications_unread"] = 0
    schedule_save()
    
    return jsonify({"ok": True})

# --- AI Dashboard ---
@app.route("/ai_dashboard")
def ai_dashboard():
    top_k = 5
    internship_matches = []
    
    for idx, it in enumerate(internships):
        req = set(it.get("skills", []))
        scores = []
        
        for s in students:
            s_sk = set(s.get("skills", []))
            overlap = len(req & s_sk)
            if overlap > 0:
                scores.append({
                    "student_id": s["id"],
                    "student_name": s["name"],
                    "overlap": overlap,
                    "skills": list(req & s_sk)
                })
        
        scores_sorted = sorted(scores, key=lambda x: x["overlap"], reverse=True)[:top_k]
        internship_matches.append({
            "iid": idx,
            "company": it.get("company"),
            "title": it.get("title"),
            "top": scores_sorted
        })
    
    totals = {"students": len(students), "internships": len(internships)}
    
    return render_template_string("""
<!doctype html><html><head><meta charset="utf-8"><title>AI Matching Dashboard</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
</head>
<body class="bg-light p-4">
  <div class="container">
    <div class="d-flex justify-content-between align-items-center mb-4">
      <div>
        <h3>AI Matching Dashboard</h3>
        <p class="text-muted">Skill-based intelligent matching between students and internships</p>
      </div>
      <a href="{{ url_for('internship_listings') }}" class="btn btn-outline-primary">
        <i class="bi bi-arrow-left me-2"></i>Back
      </a>
    </div>
    
    <div class="row mb-4">
      <div class="col-md-6">
        <div class="card">
          <div class="card-body text-center">
            <h2 class="display-4">{{ totals.students }}</h2>
            <p class="text-muted mb-0">Total Students</p>
          </div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-body text-center">
            <h2 class="display-4">{{ totals.internships }}</h2>
            <p class="text-muted mb-0">Active Internships</p>
          </div>
        </div>
      </div>
    </div>

    {% for im in internship_matches %}
      <div class="card mb-3">
        <div class="card-body">
          <h5 class="card-title">{{ im.title }} — {{ im.company }}</h5>
          {% if im.top %}
            <div class="table-responsive">
              <table class="table table-sm mb-0">
                <thead>
                  <tr>
                    <th>Student</th>
                    <th>Match Score</th>
                    <th>Matched Skills</th>
                  </tr>
                </thead>
                <tbody>
                  {% for t in im.top %}
                    <tr>
                      <td><strong>{{ t.student_name }}</strong></td>
                      <td><span class="badge bg-primary">{{ t.overlap }} skills</span></td>
                      <td>{{ t.skills|join(', ') }}</td>
                    </tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
          {% else %}
            <p class="text-muted mb-0">No matching students found</p>
          {% endif %}
        </div>
      </div>
    {% endfor %}
  </div>
</body></html>
""", internship_matches=internship_matches, totals=totals)

# --- Recommendations ---
@app.route("/recommendations")
def recommendations():
    if 'current_student_id' not in session:
        flash('Please login to view recommendations', 'warning')
        return redirect(url_for('internship_listings'))
    
    st = student_by_id(session['current_student_id'])
    if not st:
        flash('Student not found', 'error')
        return redirect(url_for('internship_listings'))

    recs = get_student_recommendations(st)
    
    return render_template_string("""
<!doctype html><html><head><meta charset="utf-8"><title>Recommendations</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
</head>
<body class="bg-light p-4">
  <div class="container">
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h3>Recommended Internships</h3>
      <a href="{{ url_for('internship_listings') }}" class="btn btn-outline-primary">
        <i class="bi bi-arrow-left me-2"></i>Back
      </a>
    </div>
    
    {% if recs %}
      <div class="row">
        {% for r in recs %}
          <div class="col-md-6 mb-4">
            <div class="card h-100">
              <div class="card-body">
                <h5 class="card-title">{{ r.title }}</h5>
                <h6 class="card-subtitle mb-3 text-muted">{{ r.company }}</h6>
                <p><strong>Matched Skills:</strong> {{ r.matched_skills|join(', ') }}</p>
                <div class="d-flex justify-content-between align-items-center">
                  <span class="badge bg-success">{{ r.match_score }}% match</span>
                  <form method="post" action="/apply">
                    <input type="hidden" name="sid" value="{{ current_user.id }}">
                    <input type="hidden" name="iid" value="{{ r.iid }}">
                    <button class="btn btn-sm btn-primary">
                      <i class="bi bi-send me-1"></i>Apply
                    </button>
                  </form>
                </div>
              </div>
            </div>
          </div>
        {% endfor %}
      </div>
    {% else %}
      <div class="alert alert-info">No recommendations found for your current skills.</div>
    {% endif %}
  </div>
</body></html>
""", recs=recs)

# Ensure data is loaded at startup
load_data()

# --- Entry point ---
if __name__ == "__main__":
    app.run(debug=True)