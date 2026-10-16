#!/usr/bin/env python3
"""
CLI script to bootstrap or reset an administrator account in MySQL for HealthHub.
Usage:
    python scripts/create_admin.py --name "Administrator" --email "your-real-admin-email@example.com" --password "use-a-strong-password"
"""

import sys
import argparse
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from werkzeug.security import generate_password_hash
from backend.database import get_db, query_db

def create_or_update_admin(name, email, password):
    email = email.strip().lower()
    name = name.strip()
    
    if not email or not password or not name:
        print("Error: Name, email, and password must not be empty.")
        sys.exit(1)

    password_hash = generate_password_hash(password)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, role FROM users WHERE email = %s", (email,))
            existing = cur.fetchone()

            if existing:
                cur.execute(
                    "UPDATE users SET name = %s, password_hash = %s, role = 'admin', status = 'active', email_verified = TRUE WHERE id = %s",
                    (name, password_hash, existing['id'])
                )
                print(f"SUCCESS: Updated existing user (ID: {existing['id']}) to administrator role.")
            else:
                cur.execute(
                    "INSERT INTO users (name, email, password_hash, role, status, email_verified) VALUES (%s, %s, %s, 'admin', 'active', TRUE)",
                    (name, email, password_hash)
                )
                print(f"SUCCESS: Created new administrator account for '{email}' (ID: {cur.lastrowid}).")

    print("Credentials ready for login at: /login.html")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Create or reset HealthHub Administrator Account")
    parser.add_argument('--name', default='HealthHub Administrator', help='Admin full name')
    parser.add_argument('--email', required=True, help='Administrator email address')
    parser.add_argument('--password', required=True, help='Strong administrator password')

    args = parser.parse_args()
    create_or_update_admin(args.name, args.email, args.password)
