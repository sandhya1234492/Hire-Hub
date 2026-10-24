import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DATABASE = os.getenv("MONGO_DATABASE", "hirehub")
    UPLOAD_FOLDER = os.getenv(
        "UPLOAD_FOLDER", str(Path(__file__).parent / "uploads" / "resumes")
    )
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(5 * 1024 * 1024)))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12
