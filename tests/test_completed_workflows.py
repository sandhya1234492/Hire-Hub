from datetime import date, timedelta

from bson import ObjectId


def test_candidate_profile_and_recommendations_use_profile_data(client, app, register_user):
    register_user(client, "CANDIDATE", "profile-flow@example.test")
    updated = client.post("/profile", data={
        "name": "Profile Candidate", "phone": "555-123-4567", "location": "Seattle",
        "skills": "Python, MongoDB", "experience_years": "2", "expected_salary": "90000",
        "notice_period": "2 weeks",
        "education": "BSc Computer Science | North University | 2020",
        "experience": "Developer | Example Labs | 2",
    })
    assert updated.status_code == 302
    candidate = app.config["MONGO_CLIENT"]["hirehub_test"]["users"].find_one(
        {"email": "profile-flow@example.test"}
    )
    assert candidate["education"] == [{
        "degree": "BSc Computer Science", "institution": "North University", "year": 2020,
    }]
    assert candidate["experience"] == [{
        "title": "Developer", "company": "Example Labs", "years": 2.0,
    }]
    assert client.get("/api/recommendations").status_code == 200
    assert client.get("/dashboard").status_code == 200


def test_recruiter_can_edit_own_job_and_company_profile(client, app, register_user):
    register_user(
        client, "RECRUITER", "edit-flow@example.test", company_name="Edit Company"
    )
    job = client.post("/api/jobs", json={
        "title": "Initial Engineer", "description": "Initial details",
        "skills": ["Python"], "salary_min": 70000, "salary_max": 100000,
    }).json["data"]
    assert client.get(f"/recruiter/jobs/{job['_id']}/edit").status_code == 200
    edited = client.post(f"/recruiter/jobs/{job['_id']}/edit", data={
        "title": "Senior Python Engineer", "description": "Updated role",
        "skills": "Python, MongoDB", "location": "Portland",
        "work_mode": "REMOTE", "employment_type": "FULL_TIME",
        "experience_min": "3", "experience_max": "6",
        "salary_min": "90000", "salary_max": "140000", "deadline": "",
    })
    assert edited.status_code == 302
    saved_job = client.get(f"/api/jobs/{job['_id']}").json["data"]
    assert saved_job["title"] == "Senior Python Engineer"
    assert saved_job["salary_min"] == 90000
    assert saved_job["skills"] == ["Python", "MongoDB"]

    database = app.config["MONGO_CLIENT"]["hirehub_test"]
    company = database["companies"].find_one({"name": "Edit Company"})
    database["companies"].update_one({"_id": company["_id"]}, {"$set": {"verified": True}})
    response = client.put("/api/recruiter/company", json={
        "name": "Edit Company Inc.", "website": "https://edit.example.test",
        "industry": "Technology", "size": "50-100",
        "location": "Portland", "description": "A fictional company.",
    })
    assert response.status_code == 200
    assert response.json["data"]["name"] == "Edit Company Inc."
    assert response.json["data"]["verified"] is False
    assert client.get("/recruiter/company").status_code == 200


def test_interview_cancellation_restores_shortlisted_status(client, app, register_user):
    register_user(client, "RECRUITER", "lifecycle@example.test", company_name="Lifecycle Co")
    job = client.post("/api/jobs", json={
        "title": "Lifecycle Engineer", "description": "Role",
    }).json["data"]
    client.post("/api/auth/logout")
    register_user(client, "CANDIDATE", "lifecycle-candidate@example.test")
    application = client.post(f"/api/jobs/{job['_id']}/apply").json["data"]
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={
        "email": "lifecycle@example.test", "password": "correct-horse-battery",
    })
    assert client.put(
        f"/api/applications/{application['_id']}/status", json={"status": "SHORTLISTED"}
    ).status_code == 200
    interview = client.post("/api/interviews", json={
        "application_id": application["_id"],
        "date": (date.today() + timedelta(days=5)).isoformat(),
        "time": "10:30", "meeting_link": "https://meet.example.test/room",
    })
    assert interview.status_code == 201
    interview_id = interview.json["data"]["_id"]
    cancelled = client.put(
        f"/api/interviews/{interview_id}", json={"status": "CANCELLED"}
    )
    assert cancelled.status_code == 200
    db = app.config["MONGO_CLIENT"]["hirehub_test"]
    assert db["applications"].find_one(
        {"_id": ObjectId(application["_id"])}
    )["status"] == "SHORTLISTED"
    assert db["notifications"].find_one({
        "user_id": db["users"].find_one({"email": "lifecycle-candidate@example.test"})["_id"],
        "message": "Your interview was cancelled.",
    })


def test_reports_are_admin_only_filterable_and_csv_safe(client, app, monkeypatch):
    client.post("/api/auth/register", json={
        "name": "=Formula Candidate", "email": "report-candidate@example.test",
        "password": "candidate-password", "role": "CANDIDATE",
    })
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={
        "name": "Report Recruiter", "email": "report-recruiter@example.test",
        "password": "candidate-password", "role": "RECRUITER",
        "company_name": "Report Labs",
    })
    job = client.post("/api/jobs", json={
        "title": "Report Engineer", "description": "Reporting job",
        "location": "Seattle", "skills": ["Python"],
    }).json["data"]
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={
        "email": "report-candidate@example.test", "password": "candidate-password",
    })
    application = client.post(f"/api/jobs/{job['_id']}/apply")
    assert application.status_code == 201
    client.post("/api/auth/logout")
    assert client.get("/admin/reports").status_code == 302
    client.post("/api/auth/login", json={
        "email": "report-candidate@example.test", "password": "candidate-password",
    })
    assert client.get("/admin/reports").status_code == 403
    assert client.get("/api/admin/reports/applications").status_code == 403
    client.post("/api/auth/logout")

    monkeypatch.setenv("HIREHUB_ADMIN_NAME", "Report Admin")
    monkeypatch.setenv("HIREHUB_ADMIN_EMAIL", "report-admin@example.test")
    monkeypatch.setenv("HIREHUB_ADMIN_PASSWORD", "a-very-strong-admin-password")
    result = app.test_cli_runner().invoke(args=["create-admin"])
    assert result.exit_code == 0, result.output
    client.post("/api/auth/login", json={
        "email": "report-admin@example.test",
        "password": "a-very-strong-admin-password",
    })
    report = client.get("/api/admin/reports/applications?status=APPLIED&company=Report&location=Seattle")
    assert report.status_code == 200
    assert len(report.json["data"]["rows"]) == 1
    page = client.get("/admin/reports?type=applications&status=APPLIED")
    assert page.status_code == 200
    csv_response = client.get("/admin/reports/applications.csv?status=APPLIED")
    assert csv_response.status_code == 200
    assert b"'=Formula Candidate" in csv_response.data


def test_stale_sessions_and_unrelated_recruiters_cannot_download_resumes(client, app, register_user):
    register_user(client, "RECRUITER", "resume-owner@example.test", company_name="Resume Owner")
    client.post("/api/auth/logout")
    register_user(client, "CANDIDATE", "resume-candidate@example.test")
    db = app.config["MONGO_CLIENT"]["hirehub_test"]
    candidate_id = db["users"].find_one({"email": "resume-candidate@example.test"})["_id"]
    resume_id = db["resumes"].insert_one({
        "candidate_id": candidate_id, "stored_name": "private.docx",
        "filename": "resume.docx", "content_type": "application/vnd.openxmlformats",
    }).inserted_id
    client.post("/api/auth/logout")
    register_user(client, "RECRUITER", "unrelated-recruiter@example.test", company_name="Unrelated")
    assert client.get(f"/resume/{resume_id}").status_code == 403
    assert client.get(f"/api/resumes/{resume_id}").status_code == 403

    client.post("/api/auth/logout")
    with client.session_transaction() as session:
        session["user_id"] = "not-an-object-id"
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/dashboard").status_code == 302


def test_candidate_can_delete_resume_from_web_profile(client, app, register_user):
    from io import BytesIO

    register_user(client, "CANDIDATE", "resume-delete@example.test")
    uploaded = client.post("/api/resumes", data={
        "resume": (BytesIO(b"%PDF-1.4 test document"), "delete-me.pdf", "application/pdf"),
    }, content_type="multipart/form-data")
    assert uploaded.status_code == 201
    resume_id = uploaded.json["data"]["_id"]
    response = client.post(f"/resume/{resume_id}/delete")
    assert response.status_code == 302
    assert app.config["MONGO_CLIENT"]["hirehub_test"]["resumes"].count_documents({}) == 0


def test_dashboard_hierarchy_and_role_navigation_are_minimal(client, app, register_user, monkeypatch):
    register_user(client, "CANDIDATE", "minimal-candidate@example.test")
    candidate_page = client.get("/dashboard")
    assert candidate_page.status_code == 200
    assert candidate_page.data.count(b'class="metric-card"') == 4
    assert b"Find Jobs" in candidate_page.data
    assert b"Recommended for you" in candidate_page.data
    assert b'class="notification-row"' not in candidate_page.data
    assert b"Saved Jobs" in candidate_page.data

    client.post("/api/auth/logout")
    register_user(
        client, "RECRUITER", "minimal-recruiter@example.test", company_name="Minimal Co"
    )
    recruiter_page = client.get("/dashboard")
    assert recruiter_page.status_code == 200
    assert recruiter_page.data.count(b'class="metric-card"') == 4
    assert b"Post a Job" in recruiter_page.data
    assert b"Applicants" in recruiter_page.data

    client.post("/api/auth/logout")
    monkeypatch.setenv("HIREHUB_ADMIN_NAME", "Minimal Admin")
    monkeypatch.setenv("HIREHUB_ADMIN_EMAIL", "minimal-admin@example.test")
    monkeypatch.setenv("HIREHUB_ADMIN_PASSWORD", "a-very-strong-admin-password")
    assert app.test_cli_runner().invoke(args=["create-admin"]).exit_code == 0
    client.post("/api/auth/login", json={
        "email": "minimal-admin@example.test",
        "password": "a-very-strong-admin-password",
    })
    admin_page = client.get("/admin/dashboard")
    assert admin_page.status_code == 200
    assert admin_page.data.count(b'class="metric-card"') == 4
    assert b"<canvas" not in admin_page.data
    assert b"Audit Logs" in admin_page.data


def test_job_search_supports_multi_skill_company_keyword_and_sort(client, app, register_user):
    register_user(
        client, "RECRUITER", "search-sort@example.test", company_name="Northstar Search"
    )
    first = client.post("/api/jobs", json={
        "title": "Python Data Analyst", "description": "Analyze products",
        "skills": ["Python", "SQL"], "salary_min": 80000, "salary_max": 110000,
    }).json["data"]
    second = client.post("/api/jobs", json={
        "title": "Python Engineer", "description": "Build services",
        "skills": ["Python"], "salary_min": 120000, "salary_max": 150000,
    }).json["data"]

    multi_skill = client.get("/api/jobs?skill=python,sql")
    assert multi_skill.status_code == 200
    assert multi_skill.json["data"]["total"] == 1
    company_keyword = client.get("/api/jobs?keyword=Northstar%20Search")
    assert company_keyword.json["data"]["total"] == 2
    highest = client.get("/api/jobs?sort=salary_desc")
    assert highest.json["data"]["items"][0]["_id"] == second["_id"]


def test_candidate_web_registration_job_search_and_application_flow(client, app):
    recruiter = client.post("/register", data={
        "name": "Web Recruiter", "email": "web-recruiter@example.test",
        "password": "recruiter-password", "confirm_password": "recruiter-password",
        "role": "RECRUITER", "company_name": "Web Flow Company",
    })
    assert recruiter.status_code == 302
    posted = client.post("/recruiter/jobs/new", data={
        "title": "UX Engineer", "description": "Build accessible web products.",
        "skills": "JavaScript, Accessibility", "location": "Austin",
        "work_mode": "HYBRID", "employment_type": "FULL_TIME",
        "experience_min": "2", "experience_max": "5",
        "salary_min": "80000", "salary_max": "120000", "deadline": "",
    })
    assert posted.status_code == 302
    job = app.config["MONGO_CLIENT"]["hirehub_test"]["jobs"].find_one(
        {"title": "UX Engineer"}
    )

    client.post("/logout")
    candidate = client.post("/register", data={
        "name": "Web Candidate", "email": "web-candidate@example.test",
        "password": "candidate-password", "confirm_password": "candidate-password",
        "role": "CANDIDATE",
    })
    assert candidate.status_code == 302
    assert client.get("/jobs?keyword=UX&location=Austin").status_code == 200
    detail = client.get(f"/jobs/{job['_id']}")
    assert detail.status_code == 200
    assert b"Apply for this job" in detail.data
    applied = client.post(f"/jobs/{job['_id']}/apply")
    assert applied.status_code == 302
    assert b"Application submitted successfully" in client.get(
        f"/jobs/{job['_id']}"
    ).data
    assert client.get("/applications").status_code == 200
