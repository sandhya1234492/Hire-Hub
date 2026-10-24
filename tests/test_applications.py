def test_candidate_can_apply_once_and_recruiter_can_review(client, register_user):
    register_user(
        client, "RECRUITER", "hiring@example.test", company_name="Orbit Works"
    )
    job = client.post("/api/jobs", json={
        "title": "Backend Engineer", "description": "Build APIs", "skills": ["Python"],
    }).json["data"]
    client.post("/api/auth/logout")
    register_user(client, "CANDIDATE", "applicant@example.test", skills=["Python"])
    first = client.post(f"/api/jobs/{job['_id']}/apply")
    assert first.status_code == 201
    assert client.post(f"/api/jobs/{job['_id']}/apply").status_code == 409
    application_id = first.json["data"]["_id"]
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={
        "email": "hiring@example.test", "password": "correct-horse-battery",
    })
    updated = client.put(
        f"/api/applications/{application_id}/status",
        json={"status": "SHORTLISTED"},
    )
    assert updated.status_code == 200
    assert updated.json["data"]["status"] == "SHORTLISTED"


def test_candidate_cannot_view_another_candidates_application(client, register_user):
    register_user(client, "RECRUITER", "hiring@example.test", company_name="Orbit Works")
    job = client.post("/api/jobs", json={
        "title": "Engineer", "description": "Role",
    }).json["data"]
    client.post("/api/auth/logout")
    register_user(client, "CANDIDATE", "first@example.test")
    application = client.post(f"/api/jobs/{job['_id']}/apply").json["data"]
    client.post("/api/auth/logout")
    register_user(client, "CANDIDATE", "second@example.test")
    response = client.get(f"/api/applications/{application['_id']}")
    assert response.status_code == 403


def test_candidate_saves_job_and_withdraws_application(client, register_user):
    register_user(
        client, "RECRUITER", "hiring@example.test", company_name="Orbit Works"
    )
    job = client.post("/api/jobs", json={
        "title": "Engineer", "description": "Role",
    }).json["data"]
    client.post("/api/auth/logout")
    register_user(client, "CANDIDATE", "candidate@example.test")
    assert client.post(f"/api/jobs/{job['_id']}/save").status_code == 200
    assert client.get("/api/auth/me").json["data"]["saved_jobs"] == [job["_id"]]
    application = client.post(f"/api/jobs/{job['_id']}/apply").json["data"]
    withdrawn = client.post(
        f"/api/applications/{application['_id']}/withdraw"
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json["data"]["status"] == "WITHDRAWN"
