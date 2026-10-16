import os
import uuid
from pathlib import Path
from datetime import datetime
from flask import Blueprint, request, jsonify, session, send_file
from werkzeug.utils import secure_filename
from backend.config import Config
from backend.database import get_db, query_db, execute_db
from backend.routes.auth_routes import login_required, role_required, csrf_protect

cert_bp = Blueprint('certificates', __name__, url_prefix='/api')

def validate_magic_bytes(file_stream, ext):
    """
    Validate that the file header bytes match the declared file extension.
    Never trust the client-supplied MIME type or extension alone.
    """
    pos = file_stream.tell()
    header = file_stream.read(16)
    file_stream.seek(pos)

    if ext == 'pdf':
        return header.startswith(b'%PDF-')
    elif ext in ['jpg', 'jpeg']:
        return header.startswith(b'\xff\xd8\xff')
    elif ext == 'png':
        return header.startswith(b'\x89PNG\r\n\x1a\n')
    return False

@cert_bp.route('/certificates/upload', methods=['POST'])
@login_required
@role_required(['doctor'])
@csrf_protect
def upload_certificate():
    """
    Secure doctor certificate upload.
    Validates extension, size, magic signature, generates UUID filename,
    and updates both certificate metadata and doctor status to 'pending' in MySQL.
    """
    user_id = session['user_id']
    doctor = query_db("SELECT id FROM doctors WHERE user_id = %s", (user_id,), one=True)
    if not doctor:
        return jsonify({'error': 'Doctor profile not found for this account.'}), 404

    doctor_id = doctor['id']

    if 'file' not in request.files:
        return jsonify({'error': 'No certificate file was attached in the request.'}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'error': 'Please select a valid certificate file.'}), 400

    cert_type = (request.form.get('certificate_type') or 'Medical Council Registration / Degree Certificate').strip()

    # 1. Validate file extension
    orig_name = secure_filename(file.filename)
    if '.' not in orig_name:
        return jsonify({'error': 'Invalid file name without extension.'}), 400

    ext = orig_name.rsplit('.', 1)[1].lower()
    if ext not in Config.ALLOWED_CERT_EXTENSIONS:
        return jsonify({'error': f'Unsupported file type. Allowed formats: {", ".join(Config.ALLOWED_CERT_EXTENSIONS).upper()}.'}), 400

    # 2. Validate file size (<= 5 MB)
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > Config.MAX_CONTENT_LENGTH:
        return jsonify({'error': 'File exceeds maximum allowed limit of 5 MB.'}), 400

    if file_size == 0:
        return jsonify({'error': 'The uploaded file is empty.'}), 400

    # 3. Validate content signature (magic bytes)
    if not validate_magic_bytes(file.stream, ext):
        return jsonify({'error': 'File content does not match the declared file type. Malformed or corrupted file.'}), 400

    # 4. Generate unique secure stored filename
    stored_filename = f"cert_{doctor_id}_{uuid.uuid4().hex}.{ext}"
    target_path = Config.UPLOAD_FOLDER / stored_filename

    # Save to private directory
    file.save(str(target_path))

    # Determine standard MIME type
    mime_map = {
        'pdf': 'application/pdf',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png'
    }
    mime_type = mime_map.get(ext, 'application/octet-stream')

    # 5. Persist to MySQL within transaction
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # Insert certificate row
                cur.execute(
                    """
                    INSERT INTO doctor_certificates 
                    (doctor_id, certificate_type, original_filename, stored_filename, file_size, mime_type, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'pending')
                    """,
                    (doctor_id, cert_type, orig_name, stored_filename, file_size, mime_type)
                )
                cert_id = cur.lastrowid

                # Reset doctor's verification status to 'pending'
                cur.execute(
                    "UPDATE doctors SET verification_status = 'pending' WHERE id = %s",
                    (doctor_id,)
                )

        return jsonify({
            'message': 'Certificate uploaded successfully. Your credentials are now pending administrator verification.',
            'certificate': {
                'id': cert_id,
                'certificate_type': cert_type,
                'original_filename': orig_name,
                'file_size': file_size,
                'status': 'pending'
            }
        }), 201

    except Exception as e:
        # Cleanup file if DB insertion failed
        if target_path.exists():
            target_path.unlink()
        return jsonify({'error': f'Database recording failed: {str(e)}'}), 500

@cert_bp.route('/certificates/<int:cert_id>/download', methods=['GET'])
@login_required
def download_certificate(cert_id):
    """
    Secure document preview/download route.
    Authorized strictly for Administrator OR the Doctor who owns this certificate.
    Public visitors and other doctors are rejected with 403 Forbidden.
    """
    current_user_id = session['user_id']
    current_role = session.get('role')

    cert = query_db(
        """
        SELECT c.*, d.user_id AS doctor_user_id 
        FROM doctor_certificates c
        JOIN doctors d ON c.doctor_id = d.id
        WHERE c.id = %s
        """,
        (cert_id,),
        one=True
    )

    if not cert:
        return jsonify({'error': 'Certificate record not found.'}), 404

    # Authorization Check
    is_admin = (current_role == 'admin')
    is_owner = (current_role == 'doctor' and cert['doctor_user_id'] == current_user_id)

    if not (is_admin or is_owner):
        return jsonify({'error': 'Access denied. You do not have permission to view this certificate.'}), 403

    file_path = Config.UPLOAD_FOLDER / cert['stored_filename']
    if not file_path.exists():
        return jsonify({'error': 'Physical document file missing on server storage.'}), 404

    return send_file(
        str(file_path),
        mimetype=cert['mime_type'],
        as_attachment=False,
        download_name=cert['original_filename']
    )

@cert_bp.route('/admin/certificates/pending', methods=['GET'])
@login_required
@role_required(['admin'])
def list_pending_certificates():
    """
    Admin endpoint to view all doctor certificates currently awaiting review.
    """
    sql = """
        SELECT 
            c.id AS certificate_id,
            c.certificate_type,
            c.original_filename,
            c.file_size,
            c.mime_type,
            c.status,
            c.created_at AS uploaded_at,
            d.id AS doctor_id,
            u.name AS doctor_name,
            u.email AS doctor_email,
            d.specialization,
            d.qualification,
            d.experience_years,
            d.city
        FROM doctor_certificates c
        JOIN doctors d ON c.doctor_id = d.id
        JOIN users u ON d.user_id = u.id
        WHERE c.status = 'pending'
        ORDER BY c.created_at ASC
    """
    pending = query_db(sql)
    return jsonify({
        'total': len(pending),
        'pending_certificates': pending
    }), 200

@cert_bp.route('/admin/certificates/<int:cert_id>/review', methods=['POST'])
@login_required
@role_required(['admin'])
@csrf_protect
def review_certificate(cert_id):
    """
    Admin verification workflow: Approve or Reject a certificate.
    If rejecting, a mandatory rejection reason is required and stored.
    Updates doctor's verification_status and records audit log.
    """
    admin_id = session['user_id']
    data = request.get_json() or {}
    action = (data.get('action') or '').strip().lower()
    rejection_reason = (data.get('rejection_reason') or '').strip()

    if action not in ['approve', 'reject']:
        return jsonify({'error': "Action must be either 'approve' or 'reject'."}), 400

    if action == 'reject' and not rejection_reason:
        return jsonify({'error': 'A detailed rejection reason is mandatory when rejecting credentials.'}), 400

    cert = query_db(
        "SELECT id, doctor_id, status FROM doctor_certificates WHERE id = %s",
        (cert_id,),
        one=True
    )
    if not cert:
        return jsonify({'error': 'Certificate not found.'}), 404

    new_status = 'verified' if action == 'approve' else 'rejected'
    now = datetime.now()

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # 1. Update certificate
                cur.execute(
                    """
                    UPDATE doctor_certificates 
                    SET status = %s, reviewed_by = %s, review_date = %s, rejection_reason = %s 
                    WHERE id = %s
                    """,
                    (new_status, admin_id, now, (rejection_reason if action == 'reject' else None), cert_id)
                )

                # 2. Update doctor profile verification_status
                cur.execute(
                    "UPDATE doctors SET verification_status = %s WHERE id = %s",
                    (new_status, cert['doctor_id'])
                )

                # 3. Record in audit_logs
                cur.execute(
                    """
                    INSERT INTO audit_logs (admin_id, action, target_type, target_id, details)
                    VALUES (%s, %s, 'doctor_certificates', %s, %s)
                    """,
                    (
                        admin_id,
                        'APPROVE_CERTIFICATE' if action == 'approve' else 'REJECT_CERTIFICATE',
                        cert_id,
                        f"Doctor ID: {cert['doctor_id']}. Reason: {rejection_reason}" if action == 'reject' else f"Doctor ID: {cert['doctor_id']} verified."
                    )
                )

        return jsonify({
            'message': f"Certificate successfully {new_status}.",
            'certificate_id': cert_id,
            'status': new_status,
            'review_date': now.strftime('%Y-%m-%d %H:%M:%S')
        }), 200

    except Exception as e:
        return jsonify({'error': f'Failed to process review: {str(e)}'}), 500
