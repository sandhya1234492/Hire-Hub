import argparse
import getpass
from datetime import datetime, timezone

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import get_database


def main():
    parser = argparse.ArgumentParser(description="Create a HireHub administrator.")
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    arguments = parser.parse_args()
    password = getpass.getpass("Admin password (minimum 12 characters): ")
    if len(password) < 12:
        parser.error("Password must contain at least 12 characters.")
    app = create_app()
    with app.app_context():
        users = get_database()["users"]
        email = arguments.email.strip().lower()
        if users.find_one({"email": email}):
            parser.error("An account with this email already exists.")
        users.insert_one({
            "name": arguments.name.strip(),
            "email": email,
            "phone": "",
            "role": "ADMIN",
            "password_hash": generate_password_hash(password),
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
        })
    print(f"Administrator account created for {email}.")


if __name__ == "__main__":
    main()
