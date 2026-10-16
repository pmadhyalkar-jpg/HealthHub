from functools import wraps
import hashlib
import secrets
import os
import re
from datetime import datetime, timedelta
from flask import current_app
from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from backend.database import get_db, query_db, execute_db
from backend.services.notifications import send_email

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

def csrf_protect(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            header_token = request.headers.get('X-CSRFToken')
            session_token = session.get('csrf_token')
            if not header_token or not session_token or header_token != session_token:
                return jsonify({'error': 'Invalid or missing CSRF token. Please refresh the page.'}), 403
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required. Please log in.'}), 401
        return f(*args, **kwargs)
    return decorated_function

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'Authentication required. Please log in.'}), 401
            user_role = session.get('role')
            if user_role not in allowed_roles:
                return jsonify({'error': f'Forbidden: Action requires one of {allowed_roles} role.'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@auth_bp.route('/register', methods=['POST'])
@csrf_protect
def register():
    """
    Register a new patient or doctor account with validation and password hashing.
    """
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    role = data.get('role') or 'patient'

    if not name or not email or not password:
        return jsonify({'error': 'Name, email, and password are required fields.'}), 400
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", email):
        return jsonify({'error': 'Enter a valid email address.'}), 400

    if role not in ['patient', 'doctor']:
        return jsonify({'error': 'Invalid role specified for public registration.'}), 400

    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters long.'}), 400

    # Check for existing email in users table
    existing = query_db("SELECT id FROM users WHERE email = %s", (email,), one=True)
    if existing:
        return jsonify({'error': 'An account with this email address already exists.'}), 409

    password_hash = generate_password_hash(password)
    verification_token = secrets.token_urlsafe(32)
    verification_hash = hashlib.sha256(verification_token.encode()).hexdigest()
    verification_expires = datetime.utcnow() + timedelta(minutes=30)

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # 1. Insert user
                cur.execute(
                    "INSERT INTO users (name, email, password_hash, role, status, email_verified, email_verification_token_hash, email_verification_expires) VALUES (%s, %s, %s, %s, 'active', FALSE, %s, %s)",
                    (name, email, password_hash, role, verification_hash, verification_expires)
                )
                user_id = cur.lastrowid

                # 2. Insert role-specific profile
                if role == 'patient':
                    phone = (data.get('phone') or '').strip()
                    gender = data.get('gender') or 'prefer_not_to_say'
                    dob = data.get('date_of_birth') or None
                    blood_group = (data.get('blood_group') or '').strip()
                    cur.execute(
                        "INSERT INTO patients (user_id, phone, gender, date_of_birth, blood_group) VALUES (%s, %s, %s, %s, %s)",
                        (user_id, phone, gender, dob, blood_group)
                    )
                elif role == 'doctor':
                    specialization = (data.get('specialization') or '').strip()
                    qualification = (data.get('qualification') or '').strip()
                    experience_years = int(data.get('experience_years') or 0)
                    fee = float(data.get('consultation_fee') or 500.00)
                    clinic_address = (data.get('clinic_address') or '').strip()
                    city = (data.get('city') or '').strip()
                    bio = (data.get('bio') or '').strip()

                    if not specialization or not qualification or not city:
                        raise ValueError('Specialization, qualification, and city are required for doctor registration.')

                    cur.execute(
                        """
                        INSERT INTO doctors (user_id, specialization, qualification, experience_years, consultation_fee, clinic_address, city, bio, verification_status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                        """,
                        (user_id, specialization, qualification, experience_years, fee, clinic_address, city, bio)
                    )

        base_url = os.getenv('PUBLIC_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')
        verify_url = f"{base_url}/verify-email.html?token={verification_token}"
        delivered = send_email(
            email,
            'Verify your HealthHub email address',
            f"Hello {name},\n\nPlease verify your email address to activate your HealthHub account: {verify_url}\n\nThis link expires in 30 minutes. If you did not create this account, you can ignore this email."
        )
        if not delivered:
            current_app.logger.warning('Development email verification URL for %s: %s', email, verify_url)
        if delivered:
            message = 'Account created. Open the verification link sent to your inbox before signing in.'
        else:
            message = 'Account created, but email delivery is not configured. For local development, open the verification link printed in the server terminal; configure SMTP for inbox delivery.'
        if role == 'doctor':
            message += ' Your professional profile will become bookable only after administrator credential verification.'
        return jsonify({'message': message, 'email_delivery_configured': delivered, 'redirect': 'login.html'}), 201

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': f'Registration failed: {str(e)}'}), 500

@auth_bp.route('/verify-email', methods=['POST'])
@csrf_protect
def verify_email():
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    if not token:
        return jsonify({'error': 'Verification token is required.'}), 400
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    user = query_db("SELECT id, email, email_verification_expires, email_verified FROM users WHERE email_verification_token_hash=%s", (token_hash,), one=True)
    if not user:
        return jsonify({'error': 'This verification link is invalid or has already been used.'}), 400
    if user.get('email_verified'):
        return jsonify({'message': 'Your email is already verified. You can sign in.'}), 200
    expiry = user.get('email_verification_expires')
    if not expiry or expiry < datetime.utcnow():
        return jsonify({'error': 'This verification link has expired. Please register again or request a new link.'}), 400
    execute_db("UPDATE users SET email_verified=TRUE, email_verification_token_hash=NULL, email_verification_expires=NULL WHERE id=%s", (user['id'],))
    return jsonify({'message': 'Email verified successfully. You can now sign in.'}), 200


@auth_bp.route('/resend-verification', methods=['POST'])
@csrf_protect
def resend_verification():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({'error': 'Email is required.'}), 400
    user = query_db("SELECT id, name, email_verified FROM users WHERE email=%s", (email,), one=True)
    # Avoid exposing whether an email is registered.
    if not user or user.get('email_verified'):
        return jsonify({'message': 'If the account exists and needs verification, a new link will be sent.'}), 200
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expiry = datetime.utcnow() + timedelta(minutes=30)
    execute_db("UPDATE users SET email_verification_token_hash=%s, email_verification_expires=%s WHERE id=%s", (token_hash, expiry, user['id']))
    base_url = os.getenv('PUBLIC_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')
    url = f'{base_url}/verify-email.html?token={token}'
    delivered = send_email(email, 'Your HealthHub email verification link', f"Hello {user['name']},\n\nVerify your email: {url}\n\nThis link expires in 30 minutes.")
    if not delivered:
        current_app.logger.warning('Development email verification URL for %s: %s', email, url)
    return jsonify({'message': 'If the account exists and needs verification, a new link will be sent.', 'email_delivery_configured': delivered}), 200


@auth_bp.route('/login', methods=['POST'])
@csrf_protect
def login():
    """
    Authenticate a user by email and password, establishing a secure session.
    """
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'Email and password are required.'}), 400

    user = query_db(
        "SELECT id, name, email, password_hash, role, status, email_verified FROM users WHERE email = %s",
        (email,),
        one=True
    )

    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Invalid email address or password.'}), 401

    if not user.get('email_verified'):
        return jsonify({'error': 'Please verify your email address before signing in. Check your inbox for the verification link.'}), 403

    if user['status'] != 'active':
        return jsonify({'error': 'This account has been deactivated or suspended. Please contact administrator.'}), 403

    # Set session
    session.permanent = True
    session['user_id'] = user['id']
    session['name'] = user['name']
    session['email'] = user['email']
    session['role'] = user['role']

    # Determine dashboard destination
    redirect_map = {
        'patient': 'patient-dashboard.html',
        'doctor': 'doctor-dashboard.html',
        'admin': 'admin-dashboard.html'
    }

    return jsonify({
        'message': 'Login successful.',
        'user': {
            'id': user['id'],
            'name': user['name'],
            'email': user['email'],
            'role': user['role']
        },
        'redirect': redirect_map.get(user['role'], 'index.html')
    }), 200

@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Clear user session auth keys while refreshing CSRF token."""
    session.pop('user_id', None)
    session.pop('name', None)
    session.pop('email', None)
    session.pop('role', None)
    import secrets
    session['csrf_token'] = secrets.token_hex(32)
    return jsonify({'message': 'Logged out successfully.', 'csrf_token': session['csrf_token']}), 200

@auth_bp.route('/me', methods=['GET'])
def get_current_user():
    """
    Return profile data of the currently authenticated user.
    """
    if 'user_id' not in session:
        return jsonify({'user': None}), 200

    user_id = session['user_id']
    user = query_db(
        "SELECT id, name, email, role, status, created_at FROM users WHERE id = %s",
        (user_id,),
        one=True
    )

    if not user:
        session.clear()
        return jsonify({'user': None}), 200

    profile_data = {'user': user}

    if user['role'] == 'patient':
        patient = query_db(
            "SELECT id, phone, gender, date_of_birth, blood_group, emergency_contact FROM patients WHERE user_id = %s",
            (user_id,),
            one=True
        )
        profile_data['patient'] = patient
    elif user['role'] == 'doctor':
        doctor = query_db(
            """
            SELECT id, specialization, qualification, experience_years, consultation_fee, 
                   clinic_address, city, bio, verification_status, profile_image 
            FROM doctors WHERE user_id = %s
            """,
            (user_id,),
            one=True
        )
        profile_data['doctor'] = doctor

    return jsonify(profile_data), 200
