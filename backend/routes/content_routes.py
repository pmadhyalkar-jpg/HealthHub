from flask import Blueprint, jsonify, request
from backend.database import query_db

content_bp = Blueprint('content', __name__, url_prefix='/api/content')

@content_bp.route('/symptoms', methods=['GET'])
def get_symptoms():
    """Fetch educational symptom guides from MySQL."""
    category = (request.args.get('category') or '').strip()
    search = (request.args.get('q') or '').strip()
    sql = "SELECT id, title, category, description, self_care_guidance, warning_signs, disclaimer FROM symptoms WHERE 1=1"
    params = []
    if category:
        sql += " AND category = %s"
        params.append(category)
    if search:
        sql += " AND (title LIKE %s OR category LIKE %s OR description LIKE %s OR self_care_guidance LIKE %s)"
        like = f"%{search}%"
        params.extend([like, like, like, like])
    sql += " ORDER BY title ASC"

    symptoms = query_db(sql, params)
    return jsonify({'total': len(symptoms), 'symptoms': symptoms}), 200

@content_bp.route('/home-remedies', methods=['GET'])
def get_home_remedies():
    """Fetch natural home wellness remedies from MySQL."""
    category = (request.args.get('category') or '').strip()
    sql = "SELECT id, title, category, description, preparation, safety_notes, contraindications FROM home_remedies WHERE publication_status = 'published'"
    params = []
    if category:
        sql += " AND category = %s"
        params.append(category)
    sql += " ORDER BY id ASC"

    remedies = query_db(sql, params)
    return jsonify({'total': len(remedies), 'remedies': remedies}), 200

@content_bp.route('/yoga', methods=['GET'])
def get_yoga():
    """
    Fetch yoga poses and meditation practices.
    Video URLs are stored in MySQL and editable via admin interface.
    """
    sql = """
        SELECT id, title, category, difficulty, description, benefits, safety_notes, steps, image_url, video_url, display_order 
        FROM yoga_poses 
        WHERE is_active = TRUE 
        ORDER BY display_order ASC, id ASC
    """
    poses = query_db(sql)
    return jsonify({'total': len(poses), 'yoga_poses': poses}), 200

@content_bp.route('/vitamins', methods=['GET'])
def get_vitamins():
    """Fetch vitamins and minerals information from MySQL."""
    nutrient_type = (request.args.get('type') or '').strip()
    sql = "SELECT id, name, nutrient_type, function_description, food_sources, deficiency_symptoms, safe_guidance, safety_disclaimer FROM vitamins_minerals"
    params = []
    if nutrient_type:
        sql += " WHERE nutrient_type = %s"
        params.append(nutrient_type)
    sql += " ORDER BY id ASC"

    nutrients = query_db(sql, params)
    return jsonify({'total': len(nutrients), 'vitamins_minerals': nutrients}), 200

@content_bp.route('/articles', methods=['GET'])
def get_articles():
    """Fetch published health articles."""
    sql = "SELECT id, title, slug, summary, category, author_name, read_time, published_at FROM articles WHERE publication_status = 'published' ORDER BY published_at DESC"
    articles = query_db(sql)
    for a in articles:
        if a.get('published_at'):
            a['published_at'] = a['published_at'].strftime('%B %d, %Y')
    return jsonify({'total': len(articles), 'articles': articles}), 200

@content_bp.route('/articles/<slug>', methods=['GET'])
def get_article_detail(slug):
    """Fetch single health article by slug."""
    sql = "SELECT id, title, slug, summary, content, category, author_name, read_time, published_at FROM articles WHERE slug = %s AND publication_status = 'published'"
    article = query_db(sql, (slug,), one=True)
    if not article:
        return jsonify({'error': 'Article not found.'}), 404
    if article.get('published_at'):
        article['published_at'] = article['published_at'].strftime('%B %d, %Y')
    return jsonify({'article': article}), 200

@content_bp.route('/faqs', methods=['GET'])
def get_faqs():
    """Fetch active FAQs from MySQL."""
    category = (request.args.get('category') or '').strip()
    sql = "SELECT id, category, question, answer, display_order FROM faqs WHERE is_active = TRUE"
    params = []
    if category:
        sql += " AND category = %s"
        params.append(category)
    sql += " ORDER BY display_order ASC, id ASC"

    faqs = query_db(sql, params)
    return jsonify({'total': len(faqs), 'faqs': faqs}), 200

@content_bp.route('/home-featured', methods=['GET'])
def get_home_featured():
    """
    Fetch homepage summary: 3 featured verified doctors, 3 wellness items, and 4 top FAQs.
    """
    doctors_sql = """
        SELECT d.id, u.name, d.specialization, d.qualification, d.experience_years, d.consultation_fee, d.city
        FROM doctors d JOIN users u ON d.user_id = u.id
        WHERE d.verification_status = 'verified' AND u.status = 'active'
        ORDER BY d.experience_years DESC
        LIMIT 3
    """
    featured_doctors = query_db(doctors_sql)
    for doc in featured_doctors:
        if doc.get('consultation_fee'):
            doc['consultation_fee'] = float(doc['consultation_fee'])

    faqs = query_db("SELECT id, question, answer FROM faqs WHERE is_active = TRUE ORDER BY display_order ASC LIMIT 4")
    poses = query_db("SELECT id, title, category, difficulty, description, video_url FROM yoga_poses WHERE is_active = TRUE ORDER BY display_order ASC LIMIT 3")

    return jsonify({
        'featured_doctors': featured_doctors,
        'faqs': faqs,
        'yoga_preview': poses
    }), 200
