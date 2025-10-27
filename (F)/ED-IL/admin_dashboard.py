# admin_dashboard.py - Modern Admin Dashboard with New Frontend
from flask import Blueprint, render_template, redirect, url_for, request, session, flash
import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Helper function to check if admin is logged in
def require_admin():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin.login'))
    return None

# ----------------------------
# Admin Login Route
# ----------------------------
@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        # Simple authentication (replace with your actual auth logic)
        # For demo: admin@example.com / admin123
        if email == 'admin@example.com' and password == 'admin123':
            session['admin_logged_in'] = True
            session['admin_email'] = email
            flash('Login successful! Welcome to the admin dashboard.', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid email or password. Please try again.', 'error')
    
    # Render the modern login template
    return render_template('admin_login.html')

# ----------------------------
# Admin Logout Route
# ----------------------------
@admin_bp.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_email', None)
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('admin.login'))

# ----------------------------
# Admin Dashboard Route
# ----------------------------
@admin_bp.route('/dashboard')
@admin_bp.route('/')
def dashboard():
    # Check if admin is logged in
    check = require_admin()
    if check:
        return check
    
    # Import data from main app
    from app import students, internships
    
    # Calculate statistics
    total_students = len(students)
    total_internships = len(internships)
    
    # Count applications by status
    accepted = 0
    total_apps = 0
    
    for it in internships:
        selected_ids = it.get('selected_ids', [])
        app_ids = it.get('app_ids', [])
        accepted += len(selected_ids)
        total_apps += len(app_ids)
    
    rejected = total_apps - accepted
    
    # Get recent applications for the table
    applications = []
    for idx, it in enumerate(internships):
        for sid in it.get('app_ids', [])[:10]:  # Limit to recent 10
            student = next((s for s in students if s['id'] == sid), None)
            if student:
                # Determine status
                if sid in it.get('selected_ids', []):
                    status = 'Accepted'
                else:
                    status = 'Pending'
                
                applications.append({
                    'student_name': student['name'],
                    'company': it['company'],
                    'position': it['title'],
                    'date': it.get('created_at', '')[:10] if it.get('created_at') else 'N/A',
                    'status': status
                })
    
    # Sort by date (most recent first) and limit to 10
    applications = sorted(applications, key=lambda x: x['date'], reverse=True)[:10]
    
    return render_template('admin_dashboard.html',
                         total_students=total_students,
                         total_internships=total_internships,
                         accepted_applications=accepted,
                         rejected_applications=rejected,
                         applications=applications)

# ----------------------------
# Admin Students Route
# ----------------------------
@admin_bp.route('/students')
def students():
    check = require_admin()
    if check:
        return check
    
    from app import students as student_list
    
    # You can create a dedicated template or use render_template_string
    from flask import render_template_string
    return render_template_string("""
{% extends "base.html" %}
{% block title %}Students - Admin Dashboard{% endblock %}
{% block content %}
<div class="container-fluid">
    <div class="row mb-4">
        <div class="col-12">
            <h1 class="h3 mb-2 fw-bold">Students Management</h1>
            <p class="text-muted mb-0">View and manage all registered students</p>
        </div>
    </div>
    
    <div class="card">
        <div class="card-body">
            <div class="table-responsive">
                <table class="table table-hover">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Name</th>
                            <th>Education</th>
                            <th>Skills</th>
                            <th>Resume</th>
                            <th>Applications</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for s in students %}
                        <tr>
                            <td>{{ s['id'] }}</td>
                            <td>{{ s['name'] }}</td>
                            <td>{{ s.get('education', 'N/A') }}</td>
                            <td>
                                {% for skill in s.get('skills', [])[:3] %}
                                    <span class="badge bg-primary">{{ skill }}</span>
                                {% endfor %}
                                {% if s.get('skills')|length > 3 %}
                                    <span class="badge bg-secondary">+{{ s.get('skills')|length - 3 }}</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if s.get('resume') %}
                                    <a href="/uploads/{{ s.get('resume') }}" target="_blank" class="btn btn-sm btn-outline-primary">
                                        <i class="bi bi-download"></i> Download
                                    </a>
                                {% else %}
                                    <span class="text-muted">-</span>
                                {% endif %}
                            </td>
                            <td>
                                {% set app_count = namespace(value=0) %}
                                {% for it in internships %}
                                    {% if s['id'] in it.get('app_ids', []) %}
                                        {% set app_count.value = app_count.value + 1 %}
                                    {% endif %}
                                {% endfor %}
                                {{ app_count.value }}
                            </td>
                            <td>
                                <button class="btn btn-sm btn-outline-secondary">
                                    <i class="bi bi-eye"></i> View
                                </button>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>
{% endblock %}
""", students=student_list, internships=__import__('app').internships)

# ----------------------------
# Admin Companies Route
# ----------------------------
@admin_bp.route('/companies')
def companies():
    check = require_admin()
    if check:
        return check
    
    from app import internships
    from flask import render_template_string
    
    return render_template_string("""
{% extends "base.html" %}
{% block title %}Companies - Admin Dashboard{% endblock %}
{% block content %}
<div class="container-fluid">
    <div class="row mb-4">
        <div class="col-12">
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <h1 class="h3 mb-2 fw-bold">Companies & Internships</h1>
                    <p class="text-muted mb-0">Manage all company internship postings</p>
                </div>
                <a href="/company/register" class="btn btn-primary">
                    <i class="bi bi-plus-circle me-2"></i>Add Internship
                </a>
            </div>
        </div>
    </div>
    
    <div class="row">
        {% for it in internships %}
        <div class="col-md-6 mb-4">
            <div class="card">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start mb-3">
                        <div>
                            <h5 class="card-title mb-1">{{ it['title'] }}</h5>
                            <p class="text-muted mb-0">{{ it['company'] }}</p>
                        </div>
                        <span class="badge bg-success">Active</span>
                    </div>
                    
                    <div class="mb-3">
                        <strong>Required Skills:</strong><br>
                        {% for skill in it['skills'] %}
                            <span class="badge bg-light text-dark me-1">{{ skill }}</span>
                        {% endfor %}
                    </div>
                    
                    <div class="row text-center mb-3">
                        <div class="col-4">
                            <div class="fw-bold">{{ it.get('openings', 1) }}</div>
                            <small class="text-muted">Openings</small>
                        </div>
                        <div class="col-4">
                            <div class="fw-bold">{{ it.get('apps')|length }}</div>
                            <small class="text-muted">Applicants</small>
                        </div>
                        <div class="col-4">
                            <div class="fw-bold">{{ it.get('selected_ids', [])|length }}</div>
                            <small class="text-muted">Selected</small>
                        </div>
                    </div>
                    
                    <div class="d-grid gap-2">
                        <a href="/allocate/{{ loop.index0 }}" class="btn btn-outline-primary btn-sm">
                            <i class="bi bi-bar-chart me-2"></i>View Allocations
                        </a>
                    </div>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
{% endblock %}
""", internships=internships)

# ----------------------------
# Admin Applications Route
# ----------------------------
@admin_bp.route('/applications')
def applications():
    check = require_admin()
    if check:
        return check
    
    from app import internships, students as student_list
    from flask import render_template_string
    
    # Build comprehensive applications list
    all_apps = []
    for it in internships:
        for sid in it.get('app_ids', []):
            student = next((s for s in student_list if s['id'] == sid), None)
            if student:
                # Determine status
                if sid in it.get('selected_ids', []):
                    status = 'Accepted'
                    status_class = 'success'
                else:
                    status = 'Pending'
                    status_class = 'warning'
                
                all_apps.append({
                    'student_id': student['id'],
                    'student_name': student['name'],
                    'company': it['company'],
                    'position': it['title'],
                    'date': it.get('created_at', '')[:10] if it.get('created_at') else 'N/A',
                    'status': status,
                    'status_class': status_class,
                    'skills': student.get('skills', [])
                })
    
    # Sort by date
    all_apps = sorted(all_apps, key=lambda x: x['date'], reverse=True)
    
    return render_template_string("""
{% extends "base.html" %}
{% block title %}Applications - Admin Dashboard{% endblock %}
{% block content %}
<div class="container-fluid">
    <div class="row mb-4">
        <div class="col-12">
            <h1 class="h3 mb-2 fw-bold">All Applications</h1>
            <p class="text-muted mb-0">View and manage all student applications</p>
        </div>
    </div>
    
    <div class="card">
        <div class="card-body">
            <div class="mb-3">
                <input type="text" class="form-control" id="searchApps" placeholder="Search by student name or company...">
            </div>
            
            <div class="table-responsive">
                <table class="table table-hover">
                    <thead>
                        <tr>
                            <th>Student</th>
                            <th>Company</th>
                            <th>Position</th>
                            <th>Skills</th>
                            <th>Applied On</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="appsTable">
                        {% for app in applications %}
                        <tr>
                            <td>{{ app.student_name }}</td>
                            <td>{{ app.company }}</td>
                            <td>{{ app.position }}</td>
                            <td>
                                {% for skill in app.skills[:2] %}
                                    <span class="badge bg-light text-dark">{{ skill }}</span>
                                {% endfor %}
                                {% if app.skills|length > 2 %}
                                    <span class="badge bg-secondary">+{{ app.skills|length - 2 }}</span>
                                {% endif %}
                            </td>
                            <td>{{ app.date }}</td>
                            <td>
                                <span class="badge bg-{{ app.status_class }}">{{ app.status }}</span>
                            </td>
                            <td>
                                <button class="btn btn-sm btn-outline-primary">
                                    <i class="bi bi-eye"></i>
                                </button>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>

<script>
document.getElementById('searchApps').addEventListener('input', function(e) {
    const searchTerm = e.target.value.toLowerCase();
    const rows = document.querySelectorAll('#appsTable tr');
    
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(searchTerm) ? '' : 'none';
    });
});
</script>
{% endblock %}
""", applications=all_apps)

# ----------------------------
# Admin Settings Route (Optional)
# ----------------------------
@admin_bp.route('/settings')
def settings():
    check = require_admin()
    if check:
        return check
    
    from flask import render_template_string
    
    return render_template_string("""
{% extends "base.html" %}
{% block title %}Settings - Admin Dashboard{% endblock %}
{% block content %}
<div class="container-fluid">
    <div class="row mb-4">
        <div class="col-12">
            <h1 class="h3 mb-2 fw-bold">Admin Settings</h1>
            <p class="text-muted mb-0">Manage your admin account and portal settings</p>
        </div>
    </div>
    
    <div class="row">
        <div class="col-lg-6">
            <div class="card mb-4">
                <div class="card-header bg-white">
                    <h5 class="mb-0">Account Information</h5>
                </div>
                <div class="card-body">
                    <form>
                        <div class="mb-3">
                            <label class="form-label">Email</label>
                            <input type="email" class="form-control" value="{{ session.get('admin_email', 'admin@example.com') }}" readonly>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Current Password</label>
                            <input type="password" class="form-control" placeholder="Enter current password">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">New Password</label>
                            <input type="password" class="form-control" placeholder="Enter new password">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Confirm New Password</label>
                            <input type="password" class="form-control" placeholder="Confirm new password">
                        </div>
                        <button type="submit" class="btn btn-primary">Update Password</button>
                    </form>
                </div>
            </div>
        </div>
        
        <div class="col-lg-6">
            <div class="card">
                <div class="card-header bg-white">
                    <h5 class="mb-0">Portal Settings</h5>
                </div>
                <div class="card-body">
                    <div class="mb-3">
                        <label class="form-label">Portal Name</label>
                        <input type="text" class="form-control" value="Smart Internship Portal">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Max Applications Per Student</label>
                        <input type="number" class="form-control" value="10">
                    </div>
                    <div class="form-check form-switch mb-3">
                        <input class="form-check-input" type="checkbox" id="allowRegistration" checked>
                        <label class="form-check-label" for="allowRegistration">
                            Allow Student Registration
                        </label>
                    </div>
                    <div class="form-check form-switch mb-3">
                        <input class="form-check-input" type="checkbox" id="emailNotif" checked>
                        <label class="form-check-label" for="emailNotif">
                            Send Email Notifications
                        </label>
                    </div>
                    <button type="submit" class="btn btn-primary">Save Settings</button>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}
""")