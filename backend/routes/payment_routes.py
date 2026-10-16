"""Simulated checkout workflow. No real payment processor or money movement is used."""
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal
from flask import Blueprint, jsonify, request, session
from backend.database import get_db, query_db
from backend.routes.auth_routes import login_required, role_required, csrf_protect
from backend.services.notifications import send_appointment_confirmation

payment_bp = Blueprint('payments', __name__, url_prefix='/api/payments')
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

def _minutes(value):
    if isinstance(value, timedelta):
        return int(value.total_seconds() // 60)
    return value.hour * 60 + value.minute


@payment_bp.route('/prepare', methods=['POST'])
@login_required
@role_required(['patient'])
@csrf_protect
def prepare_payment():
    """Create a pending appointment and test payment in one transaction."""
    data = request.get_json(silent=True) or {}
    doctor_id = data.get('doctor_id')
    date_str = (data.get('date') or '').strip()
    time_str = (data.get('time') or '').strip()
    reason = (data.get('reason') or '').strip()[:255]
    if not doctor_id or not date_str or not time_str:
        return jsonify({'error': 'Doctor, date, and time are required.'}), 400
    try:
        appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        appointment_time = datetime.strptime(time_str, '%H:%M').time()
    except ValueError:
        return jsonify({'error': 'Invalid appointment date or time.'}), 400
    if appointment_date < date.today():
        return jsonify({'error': 'Appointments cannot be booked in the past.'}), 400
    patient = query_db('SELECT id FROM patients WHERE user_id=%s', (session['user_id'],), one=True)
    if not patient:
        return jsonify({'error': 'Patient profile not found.'}), 404
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT d.id, d.consultation_fee, d.verification_status, u.status AS user_status FROM doctors d JOIN users u ON u.id=d.user_id WHERE d.id=%s FOR UPDATE", (int(doctor_id),))
                doctor = cur.fetchone()
                if not doctor or doctor['verification_status'] != 'verified' or doctor['user_status'] != 'active':
                    return jsonify({'error': 'This doctor is not available for booking.'}), 403
                day_name = DAYS[appointment_date.weekday()]
                cur.execute("SELECT id, start_time, end_time, slot_duration_minutes FROM doctor_availability WHERE doctor_id=%s AND day_of_week=%s AND is_active=TRUE", (int(doctor_id), day_name))
                rules = cur.fetchall()
                valid_slot = False
                for rule in rules:
                    start = rule['start_time']
                    end = rule['end_time']
                    slot_minutes = int(rule['slot_duration_minutes'])
                    start_minutes = _minutes(start)
                    end_minutes = _minutes(end)
                    selected_minutes = appointment_time.hour * 60 + appointment_time.minute
                    if start_minutes <= selected_minutes and selected_minutes + slot_minutes <= end_minutes and (selected_minutes-start_minutes) % slot_minutes == 0:
                        valid_slot = True
                        break
                if not valid_slot:
                    return jsonify({'error': 'The selected time is not in this doctor’s active schedule.'}), 400
                cur.execute("SELECT id FROM appointments WHERE doctor_id=%s AND appointment_date=%s AND appointment_time=%s AND status IN ('pending','confirmed') FOR UPDATE", (int(doctor_id), appointment_date, appointment_time))
                if cur.fetchone():
                    return jsonify({'error': 'This slot has just been reserved. Please choose another time.'}), 409
                cur.execute("INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, status, reason) VALUES (%s,%s,%s,%s,'pending',%s)", (patient['id'], int(doctor_id), appointment_date, appointment_time, reason or None))
                appointment_id = cur.lastrowid
                amount = Decimal(str(doctor['consultation_fee']))
                reference = 'HHTEST-' + secrets.token_hex(8).upper()
                cur.execute("INSERT INTO payments (appointment_id, patient_id, amount, currency, provider, transaction_reference, status) VALUES (%s,%s,%s,'INR','simulated',%s,'pending')", (appointment_id, patient['id'], amount, reference))
                payment_id = cur.lastrowid
        return jsonify({'message': 'Appointment slot reserved temporarily. Complete the test checkout to confirm it.', 'payment_id': payment_id, 'appointment_id': appointment_id, 'amount': float(amount), 'currency': 'INR', 'transaction_reference': reference, 'redirect': f'checkout.html?payment_id={payment_id}'}), 201
    except Exception as exc:
        # Unique active-slot index is the final concurrency guard.
        if 'Duplicate entry' in str(exc) or 'uq_active_slot' in str(exc):
            return jsonify({'error': 'This slot has just been reserved. Please choose another time.'}), 409
        raise


@payment_bp.route('/<int:payment_id>', methods=['GET'])
@login_required
@role_required(['patient'])
def payment_details(payment_id):
    row = query_db("""SELECT p.id AS payment_id, p.appointment_id, p.amount, p.currency, p.provider,
        p.transaction_reference, p.status AS payment_status, p.created_at,
        a.appointment_date, TIME_FORMAT(a.appointment_time, '%%H:%%i') AS appointment_time,
        a.status AS appointment_status, d.id AS doctor_id, du.name AS doctor_name,
        d.specialization, d.city
        FROM payments p JOIN appointments a ON a.id=p.appointment_id
        JOIN doctors d ON d.id=a.doctor_id JOIN users du ON du.id=d.user_id
        JOIN patients pat ON pat.id=p.patient_id
        WHERE p.id=%s AND pat.user_id=%s""", (payment_id, session['user_id']), one=True)
    if not row:
        return jsonify({'error': 'Payment not found.'}), 404
    for key in ('appointment_date', 'created_at'):
        if row.get(key): row[key] = row[key].isoformat()
    row['amount'] = float(row['amount'])
    return jsonify({'payment': row}), 200


@payment_bp.route('/<int:payment_id>/simulate', methods=['POST'])
@login_required
@role_required(['patient'])
@csrf_protect
def simulate_payment(payment_id):
    data = request.get_json(silent=True) or {}
    action = data.get('action')
    if action not in ('success', 'failed', 'cancel'):
        return jsonify({'error': 'Choose success, failed, or cancel.'}), 400
    patient = query_db('SELECT id FROM patients WHERE user_id=%s', (session['user_id'],), one=True)
    if not patient: return jsonify({'error': 'Patient profile not found.'}), 404
    confirmation = None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT p.id, p.appointment_id, p.amount, p.status, a.doctor_id,
                a.appointment_date, TIME_FORMAT(a.appointment_time, '%%H:%%i') AS appointment_time, a.status AS appointment_status,
                pu.name AS patient_name, pu.email AS patient_email,
                du.name AS doctor_name, du.email AS doctor_email
                FROM payments p JOIN appointments a ON a.id=p.appointment_id
                JOIN patients pat ON pat.id=p.patient_id JOIN users pu ON pu.id=pat.user_id
                JOIN doctors d ON d.id=a.doctor_id JOIN users du ON du.id=d.user_id
                WHERE p.id=%s AND p.patient_id=%s FOR UPDATE""", (payment_id, patient['id']))
            row = cur.fetchone()
            if not row: return jsonify({'error': 'Payment not found.'}), 404
            if row['status'] != 'pending':
                return jsonify({'error': 'This test transaction has already been processed.'}), 409
            if action == 'success':
                cur.execute("UPDATE payments SET status='succeeded', processed_at=NOW() WHERE id=%s", (payment_id,))
                cur.execute("UPDATE appointments SET status='confirmed' WHERE id=%s AND status='pending'", (row['appointment_id'],))
                if cur.rowcount != 1:
                    return jsonify({'error': 'The appointment is no longer pending; payment could not be applied.'}), 409
                confirmation = row
            else:
                new_status = 'failed' if action == 'failed' else 'cancelled'
                cur.execute("UPDATE payments SET status=%s, processed_at=NOW() WHERE id=%s", (new_status, payment_id))
                cur.execute("UPDATE appointments SET status='cancelled' WHERE id=%s AND status='pending'", (row['appointment_id'],))
    if action == 'success' and confirmation:
        send_appointment_confirmation(confirmation['patient_email'], confirmation['patient_name'], confirmation['doctor_email'], confirmation['doctor_name'], confirmation['appointment_id'], confirmation['appointment_date'].isoformat(), confirmation['appointment_time'], float(confirmation['amount']))
        return jsonify({'message': 'Simulated payment succeeded. Appointment confirmed.', 'status': 'succeeded', 'appointment_id': confirmation['appointment_id'], 'email_notice': 'Email is sent when SMTP is configured.'}), 200
    if action == 'failed':
        return jsonify({'message': 'Simulated payment failed. The appointment was not confirmed and the slot is released.', 'status': 'failed'}), 200
    return jsonify({'message': 'Checkout cancelled. The appointment was not confirmed and the slot is released.', 'status': 'cancelled'}), 200
