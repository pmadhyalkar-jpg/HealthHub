import re
from flask import Blueprint, request, jsonify, session
from backend.database import get_db, query_db, execute_db
from backend.routes.auth_routes import csrf_protect

interaction_bp = Blueprint('interactions', __name__, url_prefix='/api')

EMAIL_REGEX = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'

@interaction_bp.route('/contact', methods=['POST'])
@csrf_protect
def submit_contact_message():
    """
    Validate and persist public inquiries into MySQL contact_messages table.
    """
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    subject = (data.get('subject') or '').strip()
    message = (data.get('message') or '').strip()

    if not name or not email or not subject or not message:
        return jsonify({'error': 'Name, email, subject, and message are all required fields.'}), 400

    if not re.match(EMAIL_REGEX, email):
        return jsonify({'error': 'Please provide a valid email address.'}), 400

    if len(message) < 10:
        return jsonify({'error': 'Message content must be at least 10 characters long.'}), 400

    msg_id = execute_db(
        """
        INSERT INTO contact_messages (name, email, subject, message, status)
        VALUES (%s, %s, %s, %s, 'unread')
        """,
        (name, email, subject, message)
    )

    return jsonify({
        'message': 'Your message has been recorded successfully. Our support team will review it.',
        'message_id': msg_id
    }), 201

@interaction_bp.route('/feedback', methods=['POST'])
@csrf_protect
def submit_feedback():
    """
    Validate and persist user feedback and ratings (1 to 5) into MySQL.
    """
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    rating = data.get('rating')
    message = (data.get('message') or '').strip()

    if not name or not message:
        return jsonify({'error': 'Name and feedback message are required.'}), 400

    try:
        rating_int = int(rating)
        if rating_int < 1 or rating_int > 5:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({'error': 'Rating must be an integer between 1 and 5 stars.'}), 400

    user_id = session.get('user_id')

    fb_id = execute_db(
        """
        INSERT INTO feedback (user_id, name, email, rating, message, status)
        VALUES (%s, %s, %s, %s, %s, 'published')
        """,
        (user_id, name, email or None, rating_int, message)
    )

    return jsonify({
        'message': 'Thank you for your valuable feedback! Your review has been saved in the database.',
        'feedback_id': fb_id
    }), 201

@interaction_bp.route('/feedback', methods=['GET'])
def get_published_feedback():
    """
    Retrieve published user reviews from MySQL.
    """
    reviews = query_db(
        """
        SELECT id, name, rating, message, created_at 
        FROM feedback 
        WHERE status = 'published' 
        ORDER BY created_at DESC 
        LIMIT 20
        """
    )
    for r in reviews:
        if r.get('created_at'):
            r['created_at'] = r['created_at'].strftime('%B %d, %Y')

    return jsonify({'total': len(reviews), 'feedback': reviews}), 200
