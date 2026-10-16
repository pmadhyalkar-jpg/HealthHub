import os
import sys
import logging
from contextlib import contextmanager
from pathlib import Path
import pymysql
import pymysql.cursors
from backend.config import Config

logger = logging.getLogger(__name__)

class DatabaseError(Exception):
    """Custom exception raised for database configuration or query issues."""
    pass

def get_connection():
    """
    Establish a connection to the persistent MySQL database.
    Strictly forbids silent fallback to SQLite or mock in-memory stores.
    """
    try:
        conn = pymysql.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False
        )
        return conn
    except pymysql.MySQLError as err:
        error_msg = (
            f"\n=======================================================================\n"
            f"HEALTHHUB DATABASE CONNECTION ERROR:\n"
            f"Failed to connect to MySQL database '{Config.DB_NAME}' at {Config.DB_HOST}:{Config.DB_PORT}.\n"
            f"Details: {err}\n"
            f"-----------------------------------------------------------------------\n"
            f"HOW TO FIX:\n"
            f"1. Ensure MySQL Server service (e.g. MySQL80) is running.\n"
            f"2. Confirm credentials in 'backend/.env' (DB_USER, DB_PASSWORD, DB_NAME, DB_PORT).\n"
            f"3. Run 'database/schema.sql' in MySQL Workbench to initialize the schema.\n"
            f"NOTE: Per project requirements, HealthHub will NOT fall back to SQLite.\n"
            f"=======================================================================\n"
        )
        logger.error(error_msg)
        raise DatabaseError(error_msg) from err

@contextmanager
def get_db():
    """Context manager for executing dcursor.execute(atabase operations within a transaction."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query_db(query, args=(), one=False):
    """
    Execute a parameterized SELECT query against MySQL
    and return results as dictionaries.
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, args)
            results = cursor.fetchall()
            return (results[0] if results else None) if one else results


def execute_db(query, args=()):
    """
    Execute an INSERT, UPDATE, or DELETE query and return the last inserted ID.
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, args)
            return cursor.lastrowid

def execute_count(query, args=()):
    """Execute a query returning a single numeric count."""
    row = query_db(query, args, one=True)
    if row:
        return list(row.values())[0]
    return 0

def verify_connection():
    """
    Verify the MySQL connection and return diagnostic metadata.
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT VERSION() AS version, DATABASE() AS current_db, NOW() AS server_time;")
                meta = cursor.fetchone()
                cursor.execute("SHOW TABLES;")
                tables = [list(r.values())[0] for r in cursor.fetchall()]
                meta['tables'] = tables
                meta['table_count'] = len(tables)
                return True, meta
    except Exception as err:
        return False, str(err)
