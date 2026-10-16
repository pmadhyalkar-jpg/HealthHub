import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
ENV_PATH = BACKEND_DIR / '.env'
if not ENV_PATH.exists():
    ENV_PATH = PROJECT_ROOT / '.env'

load_dotenv(dotenv_path=ENV_PATH)

class Config:
    """Base application configuration."""
    PROJECT_ROOT = PROJECT_ROOT
    BACKEND_DIR = BACKEND_DIR
    SECRET_KEY = os.getenv('SECRET_KEY', 'healthhub_dev_secret_fallback_key')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    DEBUG = os.getenv('FLASK_DEBUG', '1') == '1'
    
    # Server settings
    HOST = os.getenv('FLASK_HOST', '127.0.0.1')
    PORT = int(os.getenv('FLASK_PORT', 5000))
    
    # MySQL Database settings
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', 3306))
    DB_NAME = os.getenv('DB_NAME', 'healthhub')
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    
    # Upload settings
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 5 * 1024 * 1024))  # 5 MB
    UPLOAD_FOLDER = BACKEND_DIR / os.getenv('UPLOAD_FOLDER', 'uploads_private')
    ALLOWED_CERT_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
    ALLOWED_CERT_MIMES = {'application/pdf', 'image/jpeg', 'image/png'}
    
    # Session cookie security settings
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'false').lower() in ('1', 'true', 'yes')
    EMAIL_VERIFICATION_MINUTES = int(os.getenv('EMAIL_VERIFICATION_MINUTES', '30'))
