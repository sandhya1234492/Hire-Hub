from werkzeug.security import check_password_hash


def create_admin(app, monkeypatch):
    monkeypatch.setenv("HIREHUB_ADMIN_NAME", "HireHub Administrator")
    monkeypatch.setenv("HIREHUB_ADMIN_EMAIL", "admin@example.test")
    monkeypatch.setenv("HIREHUB_ADMIN_PASSWORD", "a-very-strong-admin-password")
    return app.test_cli_runner().invoke(args=["create-admin"])


def login_as_admin(client):
    return client.post("/login", data={
        "email": "admin@example.test",
        "password": "a-very-strong-admin-password",
    })


def test_cli_creates_hashed_admin_without_removing_existing_data(app, client, monkeypatch):
    client.post("/api/auth/register", json={
        "name": "Existing Candidate", "email": "existing@example.test",
        "password": "candidate-password",
    })
    result = create_admin(app, monkeypatch)
    assert result.exit_code == 0, result.output
    database = app.config["MONGO_CLIENT"]["hirehub_test"]
    admin = database["users"].find_one({"email": "admin@example.test"})
    assert admin["role"] == "ADMIN"
    assert admin["password_hash"] != "a-very-strong-admin-password"
    assert check_password_hash(admin["password_hash"], "a-very-strong-admin-password")
    assert database["users"].find_one({"email": "existing@example.test"})
    assert database["audit_logs"].find_one({"action": "ADMIN_CREATED"})


def test_cli_requires_environment_credentials_and_rejects_duplicate(app, monkeypatch):
    for name in (
        "HIREHUB_ADMIN_NAME", "HIREHUB_ADMIN_EMAIL", "HIREHUB_ADMIN_PASSWORD"
    ):
        monkeypatch.delenv(name, raising=False)
    result = app.test_cli_runner().invoke(args=["create-admin"])
    assert result.exit_code != 0
    assert "HIREHUB_ADMIN_NAME" in result.output
    assert create_admin(app, monkeypatch).exit_code == 0
    duplicate = app.test_cli_runner().invoke(args=["create-admin"])
    assert duplicate.exit_code != 0
    assert "already exists" in duplicate.output


def test_public_web_registration_does_not_offer_or_create_admin(client, app):
    page = client.get("/register")
    assert page.status_code == 200
    assert b'value="ADMIN"' not in page.data
    response = client.post("/register", data={
        "name": "Public Admin", "email": "public-admin@example.test",
        "password": "a-very-strong-admin-password",
        "confirm_password": "a-very-strong-admin-password", "role": "ADMIN",
    })
    assert response.status_code == 400
    assert app.config["MONGO_CLIENT"]["hirehub_test"]["users"].count_documents(
        {"email": "public-admin@example.test"}
    ) == 0


def test_admin_login_redirects_to_admin_dashboard(client, app, monkeypatch):
    assert create_admin(app, monkeypatch).exit_code == 0
    response = login_as_admin(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/dashboard")
    assert client.get("/admin/dashboard").status_code == 200
    assert b"Company verification" in client.get("/admin/dashboard").data


def test_all_admin_web_and_api_routes_reject_candidates_and_recruiters(
    client, app, monkeypatch,
):
    paths = (
        "/admin/dashboard", "/admin/users", "/admin/candidates", "/admin/recruiters",
        "/admin/companies", "/admin/jobs", "/admin/applications", "/admin/analytics",
        "/admin/audit-logs",
    )
    for role, email, extra in (
        ("CANDIDATE", "candidate-admin-test@example.test", {}),
        ("RECRUITER", "recruiter-admin-test@example.test", {"company_name": "Test Co"}),
    ):
        client.post("/api/auth/register", json={
            "name": "Non-admin", "email": email, "password": "candidate-password",
            "role": role, **extra,
        })
        for path in paths:
            response = client.get(path)
            assert response.status_code == 403, (role, path, response.status_code)
        api_response = client.get("/api/admin/dashboard")
        assert api_response.status_code == 403
        assert api_response.json["error_code"] == "UNAUTHORIZED"
        client.post("/api/auth/logout")


def test_unauthed_admin_api_is_401_and_admin_management_features_work(
    client, app, monkeypatch,
):
    assert client.get("/api/admin/dashboard").status_code == 401
    client.post("/api/auth/register", json={
        "name": "Recruiter", "email": "control-recruiter@example.test",
        "password": "candidate-password", "role": "RECRUITER",
        "company_name": "Control Company",
    })
    company_id = app.config["MONGO_CLIENT"]["hirehub_test"]["companies"].find_one(
        {"name": "Control Company"}
    )["_id"]
    job = client.post("/api/jobs", json={
        "title": "Moderation Test", "description": "An open role",
    }).json["data"]
    client.post("/api/auth/logout")
    assert create_admin(app, monkeypatch).exit_code == 0
    assert login_as_admin(client).status_code == 302
    verified = client.patch(
        f"/api/admin/companies/{company_id}/verification",
        json={"verified": True},
    )
    assert verified.status_code == 200
    moderated = client.patch(
        f"/api/admin/jobs/{job['_id']}/moderation", json={"status": "CLOSED"}
    )
    assert moderated.status_code == 200
    assert moderated.json["data"]["status"] == "CLOSED"
    assert client.get("/api/admin/applications").status_code == 200
    assert client.get("/api/admin/audit-logs").status_code == 200
    assert client.get("/admin/companies").status_code == 200
    assert client.get("/admin/jobs").status_code == 200
    assert client.get("/admin/applications").status_code == 200
    assert client.get("/admin/analytics").status_code == 200
    assert client.get("/admin/audit-logs").status_code == 200
