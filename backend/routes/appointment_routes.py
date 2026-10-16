from datetime import datetime, date, timedelta
from flask import Blueprint, request, jsonify, session
import pymysql
from backend.database import get_db, query_db, execute_db
from backend.routes.auth_routes import login_required, role_required, csrf_protect

appt_bp = Blueprint('appointments', __name__, url_prefix='/api')

DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

@appt_bp.route('/appointments/slots', methods=['GET'])
def get_available_slots():
    """
    Calculate real available consultation slots for a verified doctor on a specific date.
    Excludes any slot already booked in pending or confirmed status.
    """
    doctor_id = request.args.get('doctor_id', type=int)
    date_str = (request.args.get('date') or '').strip()

    if not doctor_id or not date_str:
        return jsonify({'error': 'Doctor ID and Date (YYYY-MM-DD) are required.'}), 400

    try:
        booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

    if booking_date < date.today():
        return jsonify({'error': 'Cannot book appointments for past dates.', 'slots': []}), 400

    # Release unpaid checkout reservations after 15 minutes.
    from backend.database import execute_db
    execute_db("UPDATE appointments a LEFT JOIN payments p ON p.appointment_id=a.id SET a.status='cancelled' WHERE a.status='pending' AND a.created_at < DATE_SUB(NOW(), INTERVAL 15 MINUTE) AND (p.id IS NULL OR p.status='pending')")

    # Verify doctor exists and is verified
    doctor = query_db(
        "SELECT id, verification_status FROM doctors WHERE id = %s",
        (doctor_id,),
        one=True
    )
    if not doctor:
        return jsonify({'error': 'Doctor not found.'}), 404

    if doctor['verification_status'] != 'verified':
        return jsonify({
            'error': 'This doctor is not currently verified and cannot accept appointments.',
            'slots': []
        }), 403

    day_name = DAYS_OF_WEEK[booking_date.weekday()]

    # Query doctor's availability for that day
    avail_rules = query_db(
        """
        SELECT id, 
               TIME_FORMAT(start_time, '%%H:%%i') AS start_time, 
               TIME_FORMAT(end_time, '%%H:%%i') AS end_time, 
               slot_duration_minutes 
        FROM doctor_availability 
        WHERE doctor_id = %s AND day_of_week = %s AND is_active = TRUE
        ORDER BY start_time ASC
        """,
        (doctor_id, day_name)
    )

    if not avail_rules:
        return jsonify({
            'day': day_name,
            'message': f'Doctor has no consultation hours on {day_name}s.',
            'slots': []
        }), 200

    # Query already booked active slots for this doctor on this date
    booked_rows = query_db(
        """
        SELECT TIME_FORMAT(appointment_time, '%%H:%%i') AS booked_time 
        FROM appointments 
        WHERE doctor_id = %s AND appointment_date = %s AND status IN ('pending', 'confirmed')
        """,
        (doctor_id, date_str)
    )
    booked_times = {row['booked_time'] for row in booked_rows}

    # Generate slot intervals
    slots = []
    for rule in avail_rules:
        start_dt = datetime.strptime(rule['start_time'], '%H:%M')
        end_dt = datetime.strptime(rule['end_time'], '%H:%M')
        duration = timedelta(minutes=rule['slot_duration_minutes'])

        curr = start_dt
        while curr + duration <= end_dt:
            time_str = curr.strftime('%H:%M')
            slots.append({
                'time': time_str,
                'available': (time_str not in booked_times),
                'duration': rule['slot_duration_minutes']
            })
            curr += duration

    return jsonify({
        'doctor_id': doctor_id,
        'date': date_str,
        'day': day_name,
        'total_slots': len(slots),
        'available_slots_count': sum(1 for s in slots if s['available']),
        'slots': slots
    }), 200

@appt_bp.route('/appointments/book', methods=['POST'])
@login_required
@role_required(['patient'])
@csrf_protect
def book_appointment():
    """
    Book an appointment with atomic transaction locking and double-booking prevention.
    Strictly verifies patient identity and doctor verification status.
    """
    return jsonify({'error': 'Direct booking is disabled. Use the checkout flow to reserve and confirm an appointment.'}), 410
    user_id = session['user_id']
    patient = query_db("SELECT id FROM patients WHERE user_id = %s", (user_id,), one=True)
    if not patient:
        return jsonify({'error': 'Patient profile not found.'}), 404

    patient_id = patient['id']
    data = request.get_json() or {}
    doctor_id = data.get('doctor_id')
    date_str = (data.get('date') or '').strip()
    time_str = (data.get('time') or '').strip()
    reason = (data.get('reason') or '').strip()

    if not doctor_id or not date_str or not time_str:
        return jsonify({'error': 'Doctor, appointment date, and time slot are required.'}), 400

    try:
        appt_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

    if appt_date < date.today():
        return jsonify({'error': 'Appointments cannot be booked in the past.'}), 400

    # Format time to standard HH:MM:00
    if len(time_str) == 5:
        time_str += ":00"

    # Transaction-Safe Booking Execution
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # 1. Verify doctor is verified and lock doctor row
                cur.execute(
                    "SELECT id, verification_status, consultation_fee FROM doctors WHERE id = %s FOR UPDATE",
                    (doctor_id,)
                )
                doctor = cur.fetchone()
                if not doctor:
                    return jsonify({'error': 'Doctor does not exist.'}), 404

                if doctor['verification_status'] != 'verified':
                    return jsonify({'error': 'Appointments can only be booked with verified medical doctors.'}), 403

                # 2. Check doctor's availability schedule for that day of week
                day_name = DAYS_OF_WEEK[appt_date.weekday()]
                cur.execute(
                    """
                    SELECT id FROM doctor_availability 
                    WHERE doctor_id = %s AND day_of_week = %s 
                      AND start_time <= %s AND end_time > %s AND is_active = TRUE
                    """,
                    (doctor_id, day_name, time_str, time_str)
                )
                avail = cur.fetchone()
                if not avail:
                    return jsonify({'error': f'The selected doctor has no active availability on {day_name}s at {time_str}.'}), 400

                # 3. Prevent duplicate active booking with FOR UPDATE row lock
                cur.execute(
                    """
                    SELECT id FROM appointments 
                    WHERE doctor_id = %s AND appointment_date = %s AND appointment_time = %s 
                      AND status IN ('pending', 'confirmed') 
                    FOR UPDATE
                    """,
                    (doctor_id, date_str, time_str)
                )
                existing = cur.fetchone()
                if existing:
                    return jsonify({'error': 'This consultation time slot has already been booked. Please select another slot.'}), 409

                # 4. Insert confirmed appointment record
                cur.execute(
                    """
                    INSERT INTO appointments 
                    (patient_id, doctor_id, appointment_date, appointment_time, status, reason)
                    VALUES (%s, %s, %s, %s, 'confirmed', %s)
                    """,
                    (patient_id, doctor_id, date_str, time_str, reason)
                )
                appt_id = cur.lastrowid

        return jsonify({
            'message': 'Appointment booked successfully.',
            'appointment': {
                'id': appt_id,
                'doctor_id': doctor_id,
                'appointment_date': date_str,
                'appointment_time': time_str,
                'status': 'confirmed'
            }
        }), 201

    except pymysql.IntegrityError as ie:
        # Caught by MySQL UNIQUE KEY uq_active_slot (active_booking_key)
        return jsonify({'error': 'Slot collision: This time slot was just booked by another user.'}), 409
    except Exception as e:
        return jsonify({'error': f'Booking failed: {str(e)}'}), 500

@appt_bp.route('/patient/appointments', methods=['GET'])
@login_required
@role_required(['patient'])
def list_patient_appointments():
    """
    List all appointments belonging to the logged-in patient.
    Strict data ownership: Patients can only view their own appointments.
    """
    user_id = session['user_id']
    patient = query_db("SELECT id FROM patients WHERE user_id = %s", (user_id,), one=True)
    if not patient:
        return jsonify({'error': 'Patient record not found.'}), 404

    sql = """
        SELECT 
            a.id,
            a.appointment_date,
            TIME_FORMAT(a.appointment_time, '%%H:%%i') AS appointment_time,
            a.status,
            a.reason,
            a.notes,
            a.created_at,
            d.id AS doctor_id,
            u.name AS doctor_name,
            d.specialization,
            d.qualification,
            d.consultation_fee,
            d.clinic_address,
            d.city
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        JOIN users u ON d.user_id = u.id
        WHERE a.patient_id = %s
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """
    appointments = query_db(sql, (patient['id'],))
    for appt in appointments:
        if appt.get('consultation_fee') is not None:
            appt['consultation_fee'] = float(appt['consultation_fee'])
        if isinstance(appt.get('appointment_date'), date):
            appt['appointment_date'] = appt['appointment_date'].strftime('%Y-%m-%d')

    return jsonify({
        'total': len(appointments),
        'appointments': appointments
    }), 200

@appt_bp.route('/patient/appointments/<int:appt_id>/cancel', methods=['POST'])
@login_required
@role_required(['patient'])
@csrf_protect
def cancel_patient_appointment(appt_id):
    """
    Patient cancels their own pending or confirmed appointment.
    Frees the time slot for other patients to book.
    """
    user_id = session['user_id']
    patient = query_db("SELECT id FROM patients WHERE user_id = %s", (user_id,), one=True)
    if not patient:
        return jsonify({'error': 'Patient record not found.'}), 404

    appt = query_db(
        "SELECT id, patient_id, status FROM appointments WHERE id = %s",
        (appt_id,),
        one=True
    )
    if not appt:
        return jsonify({'error': 'Appointment not found.'}), 404

    # Strict ownership check
    if appt['patient_id'] != patient['id']:
        return jsonify({'error': 'Access denied: You can only cancel your own appointments.'}), 403

    if appt['status'] in ['cancelled', 'completed', 'rejected']:
        return jsonify({'error': f"Cannot cancel an appointment that is already {appt['status']}."}), 400

    execute_db(
        "UPDATE appointments SET status = 'cancelled' WHERE id = %s",
        (appt_id,)
    )

    return jsonify({'message': 'Appointment cancelled successfully. The slot has been released.'}), 200

@appt_bp.route('/doctor/appointments', methods=['GET'])
@login_required
@role_required(['doctor'])
def list_doctor_appointments():
    """
    List appointments scheduled with the logged-in doctor.
    Strict data ownership: Doctors can only view their own assigned appointments.
    """
    user_id = session['user_id']
    doctor = query_db("SELECT id FROM doctors WHERE user_id = %s", (user_id,), one=True)
    if not doctor:
        return jsonify({'error': 'Doctor record not found.'}), 404

    sql = """
        SELECT 
            a.id,
            a.appointment_date,
            TIME_FORMAT(a.appointment_time, '%%H:%%i') AS appointment_time,
            a.status,
            a.reason,
            a.notes,
            a.created_at,
            p.id AS patient_id,
            u.name AS patient_name,
            u.email AS patient_email,
            p.phone AS patient_phone,
            p.gender AS patient_gender,
            p.blood_group AS patient_blood_group
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN users u ON p.user_id = u.id
        WHERE a.doctor_id = %s
        ORDER BY a.appointment_date ASC, a.appointment_time ASC
    """
    appointments = query_db(sql, (doctor['id'],))
    for appt in appointments:
        if isinstance(appt.get('appointment_date'), date):
            appt['appointment_date'] = appt['appointment_date'].strftime('%Y-%m-%d')

    return jsonify({
        'total': len(appointments),
        'appointments': appointments
    }), 200

@appt_bp.route('/doctor/appointments/<int:appt_id>/status', methods=['POST'])
@login_required
@role_required(['doctor'])
@csrf_protect
def update_appointment_status_by_doctor(appt_id):
    """
    Doctor marks appointment as 'confirmed', 'completed', or 'rejected'.
    Prevents invalid status transitions.
    """
    user_id = session['user_id']
    doctor = query_db("SELECT id FROM doctors WHERE user_id = %s", (user_id,), one=True)
    if not doctor:
        return jsonify({'error': 'Doctor profile not found.'}), 404

    appt = query_db("SELECT id, doctor_id, status FROM appointments WHERE id = %s", (appt_id,), one=True)
    if not appt:
        return jsonify({'error': 'Appointment record not found.'}), 404

    if appt['doctor_id'] != doctor['id']:
        return jsonify({'error': 'Access denied: You can only update appointments assigned to you.'}), 403

    data = request.get_json() or {}
    new_status = (data.get('status') or '').strip().lower()
    notes = (data.get('notes') or '').strip()

    valid_statuses = ['confirmed', 'completed', 'rejected']
    if new_status not in valid_statuses:
        return jsonify({'error': f"Invalid status. Must be one of {valid_statuses}."}), 400

    if appt['status'] == 'completed':
        return jsonify({'error': 'Completed appointments cannot be modified.'}), 400

    execute_db(
        "UPDATE appointments SET status = %s, notes = COALESCE(NULLIF(%s, ''), notes) WHERE id = %s",
        (new_status, notes, appt_id)
    )

    return jsonify({'message': f'Appointment updated to {new_status}.', 'status': new_status}), 200

@appt_bp.route('/doctor/availability', methods=['POST'])
@login_required
@role_required(['doctor'])
@csrf_protect
def add_doctor_availability():
    """
    Add a recurring weekly schedule slot for the logged-in doctor.
    """
    user_id = session['user_id']
    doctor = query_db("SELECT id FROM doctors WHERE user_id = %s", (user_id,), one=True)
    if not doctor:
        return jsonify({'error': 'Doctor profile not found.'}), 404

    data = request.get_json() or {}
    day_of_week = (data.get('day_of_week') or '').capitalize()
    start_time = (data.get('start_time') or '').strip()
    end_time = (data.get('end_time') or '').strip()
    slot_duration = int(data.get('slot_duration_minutes') or 30)

    if day_of_week not in DAYS_OF_WEEK:
        return jsonify({'error': f'Invalid day of week. Allowed: {", ".join(DAYS_OF_WEEK)}.'}), 400

    if not start_time or not end_time:
        return jsonify({'error': 'Start time and end time are required.'}), 400

    if start_time >= end_time:
        return jsonify({'error': 'Start time must be strictly before end time.'}), 400

    slot_id = execute_db(
        """
        INSERT INTO doctor_availability (doctor_id, day_of_week, start_time, end_time, slot_duration_minutes, is_active)
        VALUES (%s, %s, %s, %s, %s, TRUE)
        """,
        (doctor['id'], day_of_week, start_time, end_time, slot_duration)
    )

    return jsonify({
        'message': 'Availability slot added successfully.',
        'slot_id': slot_id
    }), 201

@appt_bp.route('/doctor/availability/<int:slot_id>', methods=['DELETE'])
@login_required
@role_required(['doctor'])
@csrf_protect
def delete_doctor_availability(slot_id):
    """
    Remove an availability slot belonging to the doctor.
    """
    user_id = session['user_id']
    doctor = query_db("SELECT id FROM doctors WHERE user_id = %s", (user_id,), one=True)
    if not doctor:
        return jsonify({'error': 'Doctor profile not found.'}), 404

    slot = query_db("SELECT id, doctor_id FROM doctor_availability WHERE id = %s", (slot_id,), one=True)
    if not slot:
        return jsonify({'error': 'Availability slot not found.'}), 404

    if slot['doctor_id'] != doctor['id']:
        return jsonify({'error': 'Access denied: You can only delete your own availability.'}), 403

    execute_db("DELETE FROM doctor_availability WHERE id = %s", (slot_id,))
    return jsonify({'message': 'Availability slot deleted successfully.'}), 200
