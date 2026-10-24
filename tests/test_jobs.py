def test_public_search_and_recruiter_job_creation(client, register_user):
    register_user(
        client, "RECRUITER", "recruiter@example.test", company_name="Northstar Labs"
    )
    response = client.post("/api/jobs", json={
        "title": "Python Engineer", "description": "Build great software",
        "skills": ["Python", "MongoDB"], "location": "Bengaluru",
        "work_mode": "HYBRID", "employment_type": "FULL_TIME",
        "experience_min": 2, "experience_max": 5,
    })
    assert response.status_code == 201
    job_id = response.json["data"]["_id"]
    result = client.get("/api/jobs?skill=python&location=bengaluru&work_mode=HYBRID")
    assert result.status_code == 200
    assert result.json["data"]["total"] == 1
    assert client.get(f"/api/jobs/{job_id}").json["data"]["title"] == "Python Engineer"


def test_candidate_cannot_create_job(client, register_user):
    register_user(client, "CANDIDATE", "candidate@example.test")
    response = client.post("/api/jobs", json={
        "title": "Not allowed", "description": "Candidate cannot post",
    })
    assert response.status_code == 403


def test_recruiter_cannot_manage_another_recruiters_job(client, register_user):
    register_user(
        client, "RECRUITER", "first@example.test", company_name="Northstar Labs"
    )
    job_response = client.post("/api/jobs", json={
        "title": "Python Engineer", "description": "A job",
    })
    job_id = job_response.json["data"]["_id"]
    client.post("/api/auth/logout")
    register_user(
        client, "RECRUITER", "second@example.test", company_name="BrightPath"
    )
    response = client.delete(f"/api/jobs/{job_id}")
    assert response.status_code == 403


def test_public_templates_render_and_job_pagination_preserves_filters(client, app):
    database = app.config["MONGO_CLIENT"]["hirehub_test"]
    company_id = database["companies"].insert_one({"name": "Northstar Labs"}).inserted_id
    for index in range(13):
        database["jobs"].insert_one({
            "title": f"Python Engineer {index}", "description": "Backend development",
            "company_id": company_id, "recruiter_id": "recruiter",
            "skills": ["Python"], "location": "Bengaluru", "work_mode": "HYBRID",
            "employment_type": "FULL_TIME", "status": "OPEN",
        })
    for path in ("/", "/login", "/register", "/jobs?skill=Python&page=1"):
        response = client.get(path)
        assert response.status_code == 200, path
    assert b"page=2" in client.get("/jobs?skill=Python&page=1").data
