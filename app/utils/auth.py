from functools import wraps

from flask import jsonify, redirect, request, session, url_for

from app.exceptions import UnauthorizedError
from app.extensions import get_database
from app.repositories.user_repository import UserRepository


def current_user_document():
    user_id = session.get("user_id")
    return UserRepository(get_database()).get_by_id(user_id) if user_id else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user_document() if session.get("user_id") else None
        if not user or not user.get("is_active", True):
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify(success=False, message="Login required", error_code="UNAUTHORIZED"), 401
            return redirect(url_for("web.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            user = current_user_document()
            if not user or not user.get("is_active", True):
                session.clear()
                raise UnauthorizedError("This account is inactive.")
            if user.get("role") not in roles:
                raise UnauthorizedError("You do not have permission to access this resource.")
            return view(*args, **kwargs)
        return wrapped
    return decorator
