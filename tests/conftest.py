import mongomock
import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "unit-test-secret",
        "MONGO_CLIENT": mongomock.MongoClient(),
        "MONGO_DATABASE": "hirehub_test",
        "UPLOAD_FOLDER": str(tmp_path / "resumes"),
        "MAX_CONTENT_LENGTH": 5 * 1024 * 1024,
    })


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, role, email, **extra):
    data = {
        "name": "Test User",
        "email": email,
        "phone": "555-555-5555",
        "password": "correct-horse-battery",
        "confirm_password": "correct-horse-battery",
        "role": role,
        **extra,
    }
    return client.post("/api/auth/register", json=data)


@pytest.fixture
def register_user():
    return register
