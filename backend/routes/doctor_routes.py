from flask import Blueprint, request, jsonify, session
from backend.database import get_db, query_db, execute_db
from backend.routes.auth_routes import login_required, role_required, csrf_protect

doctor_bp = Blueprint('doctors', __name__, url_prefix='/api/doctors')

@doctor_bp.route('', methods=['GET'])
def list_doctors():
    """
    Fetch doctors from MySQL with search and filtering capabilities.
    All data is queried dynamically from the healthhub database.
    """
    search_query = (request.args.get('q') or '').strip()
    specialization = (request.args.get('specialization') or '').strip()
    city = (request.args.get('city') or '').strip()
    # Public directory is always restricted to active, verified practitioners.
    verified_only = True

    sql = """
        SELECT 
            d.id,
            d.user_id,
            u.name,
            u.email,
            d.specialization,
            d.qualification,
            d.experience_years,
            d.consultation_fee,
            d.clinic_address,
            d.city,
            d.bio,
            d.profile_image,
            d.verification_status,
            COALESCE(
                (SELECT GROUP_CONCAT(DISTINCT day_of_week ORDER BY FIELD(day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday') SEPARATOR ', ')
                 FROM doctor_availability 
                 WHERE doctor_id = d.id AND is_active = TRUE),
                'Schedule on request'
            ) AS available_days
        FROM doctors d
        JOIN users u ON d.user_id = u.id
        WHERE u.status = 'active'
    """
    params = []

    if verified_only:
        sql += " AND d.verification_status = 'verified'"
    elif request.args.get('status'):
        sql += " AND d.verification_status = %s"
        params.append(request.args.get('status'))

    if search_query:
        sql += " AND (u.name LIKE %s OR d.specialization LIKE %s OR d.city LIKE %s OR d.clinic_address LIKE %s)"
        like_term = f"%{search_query}%"
        params.extend([like_term, like_term, like_term, like_term])

    if specialization:
        sql += " AND d.specialization = %s"
        params.append(specialization)

    if city:
        sql += " AND d.city = %s"
        params.append(city)

    sql += " ORDER BY d.verification_status DESC, d.experience_years DESC, d.id ASC"

    doctors = query_db(sql, params)
    
    # Format decimal consultation_fee to float/number for JSON
    for doc in doctors:
        if doc['consultation_fee'] is not None:
            doc['consultation_fee'] = float(doc['consultation_fee'])

    return jsonify({
        'total': len(doctors),
        'doctors': doctors
    }), 200

@doctor_bp.route('/filters', methods=['GET'])
def get_filters():
    """
    Return distinct specializations and cities present in the database.
    """
    specializations = query_db("SELECT DISTINCT specialization FROM doctors ORDER BY specialization ASC")
    cities = query_db("SELECT DISTINCT city FROM doctors ORDER BY city ASC")

    return jsonify({
        'specializations': [s['specialization'] for s in specializations if s.get('specialization')],
        'cities': [c['city'] for c in cities if c.get('city')]
    }), 200

@doctor_bp.route('/<int:doctor_id>', methods=['GET'])
def get_doctor(doctor_id):
    """
    Fetch exact doctor profile by ID including weekly availability schedule.
    """
    sql = """
        SELECT 
            d.id,
            d.user_id,
            u.name,
            u.email,
            d.specialization,
            d.qualification,
            d.experience_years,
            d.consultation_fee,
            d.clinic_address,
            d.city,
            d.bio,
            d.profile_image,
            d.verification_status,
            d.created_at
        FROM doctors d
        JOIN users u ON d.user_id = u.id
        WHERE d.id = %s AND d.verification_status = 'verified' AND u.status = 'active'
    """
    doctor = query_db(sql, (doctor_id,), one=True)
    if not doctor:
        return jsonify({'error': f'Doctor with ID {doctor_id} not found.'}), 404

    doctor['consultation_fee'] = float(doctor['consultation_fee']) if doctor.get('consultation_fee') else 0.0

    # Fetch weekly availability
    avail_sql = """
        SELECT id, day_of_week, 
               TIME_FORMAT(start_time, '%%H:%%i') AS start_time, 
               TIME_FORMAT(end_time, '%%H:%%i') AS end_time, 
               slot_duration_minutes, is_active
        FROM doctor_availability
        WHERE doctor_id = %s AND is_active = TRUE
        ORDER BY FIELD(day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'), start_time ASC
    """
    availability = query_db(avail_sql, (doctor_id,))
    doctor['availability'] = availability

    return jsonify({'doctor': doctor}), 200

@doctor_bp.route('/my-profile', methods=['GET'])
@login_required
@role_required(['doctor'])
def get_my_doctor_profile():
    """
    Get profile for the currently logged-in doctor.
    """
    user_id = session['user_id']
    doctor = query_db("SELECT * FROM doctors WHERE user_id = %s", (user_id,), one=True)
    if not doctor:
        return jsonify({'error': 'Doctor profile not found for this user account.'}), 404

    doctor['consultation_fee'] = float(doctor['consultation_fee']) if doctor.get('consultation_fee') else 0.0

    # Certificate details
    cert = query_db(
        "SELECT id, certificate_type, original_filename, file_size, status, review_date, rejection_reason, created_at "
        "FROM doctor_certificates WHERE doctor_id = %s ORDER BY id DESC LIMIT 1",
        (doctor['id'],),
        one=True
    )
    doctor['certificate'] = cert

    # Availability
    avail = query_db(
        "SELECT id, day_of_week, TIME_FORMAT(start_time, '%%H:%%i') AS start_time, "
        "TIME_FORMAT(end_time, '%%H:%%i') AS end_time, slot_duration_minutes, is_active "
        "FROM doctor_availability WHERE doctor_id = %s ORDER BY FIELD(day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')",
        (doctor['id'],)
    )
    doctor['availability'] = avail

    return jsonify({'doctor': doctor}), 200

@doctor_bp.route('/my-profile', methods=['PUT'])
@login_required
@role_required(['doctor'])
@csrf_protect
def update_my_doctor_profile():
    """
    Update profile details for the currently logged-in doctor.
    """
    user_id = session['user_id']
    doctor = query_db("SELECT id FROM doctors WHERE user_id = %s", (user_id,), one=True)
    if not doctor:
        return jsonify({'error': 'Doctor profile not found.'}), 404

    data = request.get_json() or {}
    specialization = (data.get('specialization') or '').strip()
    qualification = (data.get('qualification') or '').strip()
    experience_years = int(data.get('experience_years') or 0)
    fee = float(data.get('consultation_fee') or 500.0)
    clinic_address = (data.get('clinic_address') or '').strip()
    city = (data.get('city') or '').strip()
    bio = (data.get('bio') or '').strip()

    if not specialization or not qualification or not city:
        return jsonify({'error': 'Specialization, qualification, and city are mandatory.'}), 400

    execute_db(
        """
        UPDATE doctors 
        SET specialization = %s, qualification = %s, experience_years = %s, 
            consultation_fee = %s, clinic_address = %s, city = %s, bio = %s
        WHERE id = %s
        """,
        (specialization, qualification, experience_years, fee, clinic_address, city, bio, doctor['id'])
    )

    return jsonify({'message': 'Doctor profile updated successfully.'}), 200
