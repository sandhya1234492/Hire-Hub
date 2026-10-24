import os
import re
from datetime import datetime, timezone

import click
from werkzeug.security import generate_password_hash

from app.extensions import get_database


def register_commands(app):
    @app.cli.command("create-admin")
    def create_admin():
        """Create the first admin from HIREHUB_ADMIN_* environment variables."""
        name = os.getenv("HIREHUB_ADMIN_NAME", "").strip()
        email = os.getenv("HIREHUB_ADMIN_EMAIL", "").strip().lower()
        password = os.getenv("HIREHUB_ADMIN_PASSWORD", "")
        if not name or len(name) > 120:
            raise click.ClickException("Set HIREHUB_ADMIN_NAME (1-120 characters).")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise click.ClickException("Set a valid HIREHUB_ADMIN_EMAIL.")
        if len(password) < 12:
            raise click.ClickException(
                "Set HIREHUB_ADMIN_PASSWORD to a password with at least 12 characters."
            )

        users = get_database()["users"]
        if users.find_one({"email": email}):
            raise click.ClickException("An account with this email already exists.")
        now = datetime.now(timezone.utc)
        user_id = users.insert_one({
            "name": name,
            "email": email,
            "phone": "",
            "role": "ADMIN",
            "password_hash": generate_password_hash(password),
            "is_active": True,
            "created_at": now,
        }).inserted_id
        get_database()["audit_logs"].insert_one({
            "user_id": user_id,
            "action": "ADMIN_CREATED",
            "resource": "user",
            "resource_id": user_id,
            "timestamp": now,
            "metadata": {},
        })
        click.echo(f"Admin account created for {email}.")
