import re
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from app.exceptions import (
    InvalidCredentialsError,
    UserAlreadyExistsError,
    ValidationError,
)
from app.repositories.user_repository import UserRepository
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService


class AuthService:
    def __init__(self, database):
        self.database = database
        self.users = UserRepository(database)

    def register(self, data):
        name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        phone = str(data.get("phone", "")).strip()
        password = str(data.get("password", ""))
        role = str(data.get("role", "CANDIDATE")).upper()
        if not name or len(name) > 120:
            raise ValidationError("Enter a name no longer than 120 characters.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValidationError("Enter a valid email address.")
        if len(password) < 8:
            raise ValidationError("Password must contain at least 8 characters.")
        if data.get("confirm_password") is not None and password != data.get("confirm_password"):
            raise ValidationError("Passwords do not match.")
        if phone and not re.fullmatch(r"[+()\d .-]{7,25}", phone):
            raise ValidationError("Enter a valid phone number.")
        if role not in {"CANDIDATE", "RECRUITER"}:
            raise ValidationError("Only candidate and recruiter registration is available.")
        if self.users.get_by_email(email):
            raise UserAlreadyExistsError("An account with this email already exists.")

        now = datetime.now(timezone.utc)
        document = {
            "name": name,
            "email": email,
            "phone": phone,
            "role": role,
            "password_hash": generate_password_hash(password),
            "is_active": True,
            "created_at": now,
        }
        if role == "CANDIDATE":
            document.update({
                "location": str(data.get("location", "")).strip(),
                "skills": self._skills(data.get("skills", [])),
                "experience_years": 0,
                "saved_jobs": [],
            })
            self.database["candidates"].insert_one({"user_email": email, "created_at": now})
        else:
            company_name = str(data.get("company_name", "")).strip()
            if not company_name:
                raise ValidationError("Company name is required for recruiter accounts.")
            company = self.database["companies"].find_one({"name": company_name})
            if not company:
                company_id = self.database["companies"].insert_one({
                    "name": company_name,
                    "verified": False,
                    "created_at": now,
                }).inserted_id
            else:
                company_id = company["_id"]
            document["company_id"] = company_id
            self.database["recruiters"].insert_one({
                "user_email": email,
                "company_id": company_id,
                "created_at": now,
            })
        user_id = self.users.insert(document)
        AuditService(self.database).record(user_id, "USER_REGISTERED", "user", user_id)
        NotificationService(self.database).create(
            user_id, "Welcome to HireHub. Complete your profile to get started.", "REGISTRATION"
        )
        document["_id"] = user_id
        return document

    def authenticate(self, email, password):
        user = self.users.get_by_email(str(email or "").strip().lower())
        if not user or not user.get("is_active", True) or not check_password_hash(
            user["password_hash"], str(password or "")
        ):
            raise InvalidCredentialsError("Email or password is incorrect.")
        AuditService(self.database).record(user["_id"], "USER_LOGIN", "user", user["_id"])
        return user

    @staticmethod
    def _skills(value):
        if isinstance(value, str):
            value = value.split(",")
        if not isinstance(value, list):
            raise ValidationError("Skills must be a list or comma-separated text.")
        return list(dict.fromkeys(
            str(skill).strip()[:60] for skill in value if str(skill).strip()
        ))[:40]
