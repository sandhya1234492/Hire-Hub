from werkzeug.security import check_password_hash


def test_register_hashes_password_and_creates_candidate(client, app):
    response = client.post("/api/auth/register", json={
        "name": "Avery Morgan", "email": "avery@example.test",
        "password": "correct-horse-battery", "confirm_password": "correct-horse-battery",
        "role": "CANDIDATE",
    })
    assert response.status_code == 201
    user = app.config["MONGO_CLIENT"]["hirehub_test"]["users"].find_one(
        {"email": "avery@example.test"}
    )
    assert user["password_hash"] != "correct-horse-battery"
    assert check_password_hash(user["password_hash"], "correct-horse-battery")
    assert response.json["data"]["role"] == "CANDIDATE"
    assert "password_hash" not in response.json["data"]


def test_duplicate_email_and_admin_registration_are_rejected(client):
    payload = {
        "name": "Test User", "email": "same@example.test",
        "password": "correct-horse-battery", "role": "CANDIDATE",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 201
    assert client.post("/api/auth/register", json=payload).status_code == 409
    payload.update(email="admin@example.test", role="ADMIN")
    assert client.post("/api/auth/register", json=payload).status_code == 400


def test_login_logout_and_me(client, register_user):
    register_user(client, "CANDIDATE", "login@example.test")
    client.post("/api/auth/logout")
    login_response = client.post("/api/auth/login", json={
        "email": "login@example.test", "password": "correct-horse-battery",
    })
    assert login_response.status_code == 200
    assert client.get("/api/auth/me").json["data"]["email"] == "login@example.test"
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_login_rejects_wrong_password(client, register_user):
    register_user(client, "CANDIDATE", "wrong@example.test")
    response = client.post("/api/auth/login", json={
        "email": "wrong@example.test", "password": "incorrect-password",
    })
    assert response.status_code == 401
    assert response.json["error_code"] == "INVALID_CREDENTIALS"


def test_candidate_and_recruiter_pages_render(client, register_user):
    register_user(client, "CANDIDATE", "candidate-pages@example.test")
    for path in ("/dashboard", "/profile", "/applications", "/saved-jobs",
                 "/interviews", "/notifications"):
        response = client.get(path)
        assert response.status_code == 200, path
    client.post("/api/auth/logout")
    register_user(
        client, "RECRUITER", "recruiter-pages@example.test",
        company_name="Page Test Company",
    )
    assert client.get("/dashboard").status_code == 200
    assert client.get("/recruiter/jobs").status_code == 200
