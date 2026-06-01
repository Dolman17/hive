"""Production-safe seed script for The Hive.

This script creates or updates the initial admin user from environment variables.
It does not create demo users, fake consultants, fake leads, fake enquiries, or sample data.

Required environment variables:
- ADMIN_EMAIL
- ADMIN_PASSWORD
- ADMIN_NAME

Usage:
    python seed_production.py
"""

import os
import sys

from app import app
from extensions import db
from models import User


REQUIRED_ENV_VARS = ["ADMIN_EMAIL", "ADMIN_PASSWORD", "ADMIN_NAME"]


def get_required_env(name):
    value = os.environ.get(name, "").strip()

    if not value:
        print(f"ERROR: Missing required environment variable: {name}")
        return None

    return value


def main():
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name, "").strip()]

    if missing:
        print("ERROR: Production seed aborted. Missing environment variables:")
        for name in missing:
            print(f"- {name}")
        return 1

    admin_email = get_required_env("ADMIN_EMAIL").lower()
    admin_password = get_required_env("ADMIN_PASSWORD")
    admin_name = get_required_env("ADMIN_NAME")

    with app.app_context():
        existing_user = User.query.filter_by(email=admin_email).first()

        if existing_user:
            existing_user.name = admin_name
            existing_user.role = "admin"
            existing_user.is_active = True

            if admin_password:
                existing_user.set_password(admin_password)

            db.session.commit()
            print(f"Admin user updated: {admin_email}")
            return 0

        admin_user = User(
            email=admin_email,
            name=admin_name,
            role="admin",
            is_active=True,
        )
        admin_user.set_password(admin_password)

        db.session.add(admin_user)
        db.session.commit()

        print(f"Admin user created: {admin_email}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
