import os
import secrets
from pathlib import Path
from flask import Flask, jsonify, request, session, send_from_directory, render_template_string
from backend.config import Config
from backend.database import verify_connection, DatabaseError

def create_app():
    """Application factory for HealthHub Flask backend."""
    app = Flask(
        __name__,
        static_folder=str(Config.PROJECT_ROOT / 'frontend'),
        static_url_path=''
    )
    
    app.config.from_object(Config)
    
    # Register API Blueprints
    from backend.routes.auth_routes import auth_bp
    from backend.routes.doctor_routes import doctor_bp
    from backend.routes.certificate_routes import cert_bp
    from backend.routes.appointment_routes import appt_bp
    from backend.routes.content_routes import content_bp
    from backend.routes.interaction_routes import interaction_bp
    from backend.routes.admin_routes import admin_bp
    from backend.routes.payment_routes import payment_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(cert_bp)
    app.register_blueprint(appt_bp)
    app.register_blueprint(content_bp)
    app.register_blueprint(interaction_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(payment_bp)
    
    # Ensure private upload folder exists
    Config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    
    # CSRF token generator & session helper
    @app.before_request
    def ensure_csrf_token():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(32)

    # Security Headers Middleware
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response

    # -----------------------------------------------------------------
    # Diagnostic & Health Check Routes
    # -----------------------------------------------------------------
    @app.route('/api/health', methods=['GET'])
    def health_check():
        db_ok, meta = verify_connection()
        return jsonify({
            'status': 'healthy' if db_ok else 'database_disconnected',
            'application': 'HealthHub Healthcare & Wellness Platform',
            'database': {
                'connected': db_ok,
                'engine': 'MySQL Server 8.0',
                'details': meta if db_ok else None,
                'error': None if db_ok else str(meta)
            }
        }), (200 if db_ok else 503)

    @app.route('/api/csrf-token', methods=['GET'])
    def get_csrf():
        """Provide CSRF token to frontend for state-changing operations."""
        return jsonify({'csrf_token': session.get('csrf_token')})

    # -----------------------------------------------------------------
    # Frontend Static File Serving
    # -----------------------------------------------------------------
    @app.route('/', defaults={'path': 'index.html'})
    @app.route('/<path:path>')
    def serve_frontend(path):
        frontend_dir = Config.PROJECT_ROOT / 'frontend'
        target_file = frontend_dir / path
        
        # If path is a file in frontend, serve it
        if target_file.is_file():
            return send_from_directory(str(frontend_dir), path)
            
        # If path without .html exists, serve it
        html_file = frontend_dir / f"{path}.html"
        if html_file.is_file():
            return send_from_directory(str(frontend_dir), f"{path}.html")
            
        # Default fallback to index.html for root or 404
        if (frontend_dir / 'index.html').is_file():
            return send_from_directory(str(frontend_dir), 'index.html')
            
        return jsonify({'error': 'Page not found'}), 404

    # -----------------------------------------------------------------
    # Error Handlers
    # -----------------------------------------------------------------
    @app.errorhandler(DatabaseError)
    def handle_db_error(err):
        return jsonify({
            'error': 'Database error occurred',
            'message': str(err),
            'suggestion': 'Verify that MySQL Server is running and schema is imported.'
        }), 503

    @app.errorhandler(404)
    def handle_404(err):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Endpoint not found', 'path': request.path}), 404
        return send_from_directory(str(Config.PROJECT_ROOT / 'frontend'), 'index.html')

    @app.errorhandler(500)
    def handle_500(err):
        return jsonify({'error': 'Internal server error'}), 500

    return app

if __name__ == '__main__':
    application = create_app()
    print(f"\n=======================================================")
    print(f" HealthHub Backend running at http://{Config.HOST}:{Config.PORT}")
    print(f" MySQL connected to '{Config.DB_NAME}' at {Config.DB_HOST}:{Config.DB_PORT}")
    print(f"=======================================================\n")
    application.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
