from flask import Blueprint, request, jsonify, session
from backend.database import get_db, query_db, execute_db
from backend.routes.auth_routes import login_required, role_required, csrf_protect

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

@admin_bp.before_request
@login_required
@role_required(['admin'])
def enforce_admin_access():
    """Ensure every route in this blueprint requires valid Administrator role."""
    pass

@admin_bp.route('/overview', methods=['GET'])
def get_admin_overview():
    """
    Return live, database-driven counts from MySQL.
    Strictly forbids hardcoded numbers or fake platform statistics.
    """
    # 1. User counts
    users_stats = query_db("""
        SELECT 
            COUNT(*) AS total_users,
            SUM(CASE WHEN role = 'patient' THEN 1 ELSE 0 END) AS total_patients,
            SUM(CASE WHEN role = 'doctor' THEN 1 ELSE 0 END) AS total_doctors,
            SUM(CASE WHEN role = 'admin' THEN 1 ELSE 0 END) AS total_admins
        FROM users
    """, one=True)

    # 2. Doctor verification breakdown
    doctor_stats = query_db("""
        SELECT 
            SUM(CASE WHEN verification_status = 'verified' THEN 1 ELSE 0 END) AS verified_doctors,
            SUM(CASE WHEN verification_status = 'pending' THEN 1 ELSE 0 END) AS pending_doctors,
            SUM(CASE WHEN verification_status = 'rejected' THEN 1 ELSE 0 END) AS rejected_doctors
        FROM doctors
    """, one=True)

    # 3. Appointments stats
    appt_stats = query_db("""
        SELECT 
            COUNT(*) AS total_appointments,
            SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END) AS confirmed_appointments,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_appointments,
            SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_appointments,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_appointments
        FROM appointments
    """, one=True)

    # 4. Pending reviews, unread inquiries, and feedback
    pending_certs = query_db("SELECT COUNT(*) AS cnt FROM doctor_certificates WHERE status = 'pending'", one=True)['cnt']
    unread_contacts = query_db("SELECT COUNT(*) AS cnt FROM contact_messages WHERE status = 'unread'", one=True)['cnt']
    total_feedback = query_db("SELECT COUNT(*) AS cnt FROM feedback", one=True)['cnt']

    return jsonify({
        'users': {
            'total': int(users_stats['total_users'] or 0),
            'patients': int(users_stats['total_patients'] or 0),
            'doctors': int(users_stats['total_doctors'] or 0),
            'admins': int(users_stats['total_admins'] or 0)
        },
        'doctors': {
            'verified': int(doctor_stats['verified_doctors'] or 0),
            'pending': int(doctor_stats['pending_doctors'] or 0),
            'rejected': int(doctor_stats['rejected_doctors'] or 0)
        },
        'appointments': {
            'total': int(appt_stats['total_appointments'] or 0),
            'confirmed': int(appt_stats['confirmed_appointments'] or 0),
            'pending': int(appt_stats['pending_appointments'] or 0),
            'cancelled': int(appt_stats['cancelled_appointments'] or 0),
            'completed': int(appt_stats['completed_appointments'] or 0)
        },
        'pending_certificates': int(pending_certs),
        'unread_contacts': int(unread_contacts),
        'total_feedback': int(total_feedback)
    }), 200

@admin_bp.route('/doctors', methods=['GET'])
def list_doctors_admin():
    """List all doctors with verification status filter."""
    status_filter = (request.args.get('status') or '').strip().lower()
    sql = """
        SELECT 
            d.id AS doctor_id,
            d.user_id,
            u.name,
            u.email,
            d.specialization,
            d.qualification,
            d.experience_years,
            d.consultation_fee,
            d.city,
            d.verification_status,
            d.created_at,
            (SELECT id FROM doctor_certificates WHERE doctor_id = d.id ORDER BY id DESC LIMIT 1) AS latest_cert_id,
            (SELECT status FROM doctor_certificates WHERE doctor_id = d.id ORDER BY id DESC LIMIT 1) AS latest_cert_status
        FROM doctors d
        JOIN users u ON d.user_id = u.id
    """
    params = []
    if status_filter in ['verified', 'pending', 'rejected']:
        sql += " WHERE d.verification_status = %s"
        params.append(status_filter)
    sql += " ORDER BY d.created_at DESC"

    doctors = query_db(sql, params)
    for doc in doctors:
        if doc.get('consultation_fee') is not None:
            doc['consultation_fee'] = float(doc['consultation_fee'])

    return jsonify({'total': len(doctors), 'doctors': doctors}), 200

@admin_bp.route('/users', methods=['GET'])
def list_users_admin():
    """List all user accounts in the platform."""
    role = (request.args.get('role') or '').strip().lower()
    sql = "SELECT id, name, email, role, status, created_at FROM users"
    params = []
    if role in ['patient', 'doctor', 'admin']:
        sql += " WHERE role = %s"
        params.append(role)
    sql += " ORDER BY id ASC"

    users = query_db(sql, params)
    return jsonify({'total': len(users), 'users': users}), 200

@admin_bp.route('/users/<int:user_id>/status', methods=['POST'])
@csrf_protect
def update_user_status(user_id):
    """Suspend or reactivate a user account."""
    admin_id = session['user_id']
    if user_id == admin_id:
        return jsonify({'error': 'You cannot deactivate your own administrative account.'}), 400

    data = request.get_json() or {}
    new_status = data.get('status')
    if new_status not in ['active', 'inactive', 'suspended']:
        return jsonify({'error': 'Invalid status.'}), 400

    execute_db("UPDATE users SET status = %s WHERE id = %s", (new_status, user_id))

    execute_db(
        "INSERT INTO audit_logs (admin_id, action, target_type, target_id, details) VALUES (%s, 'UPDATE_USER_STATUS', 'users', %s, %s)",
        (admin_id, user_id, f"Changed status to {new_status}")
    )

    return jsonify({'message': f'User account status updated to {new_status}.'}), 200

@admin_bp.route('/appointments', methods=['GET'])
def list_appointments_admin():
    """List all appointments in the system."""
    sql = """
        SELECT 
            a.id,
            a.appointment_date,
            TIME_FORMAT(a.appointment_time, '%%H:%%i') AS appointment_time,
            a.status,
            a.reason,
            a.created_at,
            u_p.name AS patient_name,
            u_p.email AS patient_email,
            u_d.name AS doctor_name,
            d.specialization,
            d.consultation_fee
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN users u_p ON p.user_id = u_p.id
        JOIN doctors d ON a.doctor_id = d.id
        JOIN users u_d ON d.user_id = u_d.id
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
        LIMIT 50
    """
    appts = query_db(sql)
    for a in appts:
        if a.get('consultation_fee'):
            a['consultation_fee'] = float(a['consultation_fee'])
    return jsonify({'total': len(appts), 'appointments': appts}), 200

@admin_bp.route('/contacts', methods=['GET'])
def list_contacts_admin():
    """List inquiries sent through contact page."""
    messages = query_db("SELECT * FROM contact_messages ORDER BY created_at DESC")
    return jsonify({'total': len(messages), 'messages': messages}), 200

@admin_bp.route('/contacts/<int:msg_id>/status', methods=['POST'])
@csrf_protect
def update_contact_status(msg_id):
    data = request.get_json() or {}
    status = data.get('status')
    if status not in ['unread', 'read', 'responded', 'archived']:
        return jsonify({'error': 'Invalid contact message status.'}), 400

    execute_db("UPDATE contact_messages SET status = %s WHERE id = %s", (status, msg_id))
    return jsonify({'message': f'Message marked as {status}.'}), 200

@admin_bp.route('/feedback', methods=['GET'])
def list_feedback_admin():
    reviews = query_db("SELECT * FROM feedback ORDER BY created_at DESC")
    return jsonify({'total': len(reviews), 'feedback': reviews}), 200

@admin_bp.route('/feedback/<int:fb_id>/status', methods=['POST'])
@csrf_protect
def toggle_feedback_status(fb_id):
    data = request.get_json() or {}
    status = data.get('status')
    if status not in ['published', 'hidden']:
        return jsonify({'error': 'Invalid feedback status.'}), 400

    execute_db("UPDATE feedback SET status = %s WHERE id = %s", (status, fb_id))
    return jsonify({'message': f'Feedback marked as {status}.'}), 200

@admin_bp.route('/yoga', methods=['GET'])
def list_yoga_admin():
    poses = query_db("SELECT * FROM yoga_poses ORDER BY display_order ASC")
    return jsonify({'total': len(poses), 'yoga_poses': poses}), 200

@admin_bp.route('/yoga/<int:pose_id>', methods=['PUT'])
@csrf_protect
def update_yoga_pose(pose_id):
    """
    Allow administrator to edit yoga content and YouTube video links without altering HTML.
    Per Master Prompt requirement: 'Keep video links editable through MySQL/admin tools'.
    """
    data = request.get_json() or {}
    video_url = (data.get('video_url') or '').strip()
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    difficulty = (data.get('difficulty') or '').strip()

    if not video_url:
        return jsonify({'error': 'Video URL cannot be empty.'}), 400

    execute_db(
        """
        UPDATE yoga_poses 
        SET video_url = %s, title = COALESCE(NULLIF(%s, ''), title), 
            description = COALESCE(NULLIF(%s, ''), description),
            difficulty = COALESCE(NULLIF(%s, ''), difficulty)
        WHERE id = %s
        """,
        (video_url, title, description, difficulty, pose_id)
    )

    admin_id = session['user_id']
    execute_db(
        "INSERT INTO audit_logs (admin_id, action, target_type, target_id, details) VALUES (%s, 'UPDATE_YOGA_LINK', 'yoga_poses', %s, %s)",
        (admin_id, pose_id, f"Updated video link to: {video_url}")
    )

    return jsonify({'message': 'Yoga practice and video URL updated successfully in MySQL.'}), 200

@admin_bp.route('/audit-logs', methods=['GET'])
def list_audit_logs():
    """Retrieve recent sensitive administrative audit trail."""
    logs = query_db("""
        SELECT a.id, a.action, a.target_type, a.target_id, a.details, a.created_at, u.name AS admin_name
        FROM audit_logs a
        LEFT JOIN users u ON a.admin_id = u.id
        ORDER BY a.created_at DESC
        LIMIT 50
    """)
    return jsonify({'total': len(logs), 'audit_logs': logs}), 200
