def test_shortlisted_candidate_can_be_scheduled_and_notified(client, register_user):
    register_user(
        client, "RECRUITER", "interviewer@example.test", company_name="Interview Co"
    )
    job = client.post("/api/jobs", json={
        "title": "Backend Engineer", "description": "Build APIs",
    }).json["data"]
    recruiter_id = client.get("/api/auth/me").json["data"]["_id"]
    client.post("/api/auth/logout")
    register_user(client, "CANDIDATE", "interviewee@example.test")
    application = client.post(f"/api/jobs/{job['_id']}/apply").json["data"]
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={
        "email": "interviewer@example.test", "password": "correct-horse-battery",
    })
    assert client.post("/api/interviews", json={
        "application_id": application["_id"], "date": "2026-12-01", "time": "10:30",
    }).status_code == 400
    assert client.put(
        f"/api/applications/{application['_id']}/status", json={"status": "SHORTLISTED"}
    ).status_code == 200
    created = client.post("/api/interviews", json={
        "application_id": application["_id"], "date": "2026-12-01", "time": "10:30",
        "type": "ONLINE", "meeting_link": "https://meet.example.test/room",
    })
    assert created.status_code == 201
    interview_id = created.json["data"]["_id"]
    assert client.put(
        f"/api/interviews/{interview_id}", json={"status": "CANCELLED"}
    ).status_code == 200
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={
        "email": "interviewee@example.test", "password": "correct-horse-battery",
    })
    interviews = client.get("/api/interviews").json["data"]["items"]
    assert len(interviews) == 1
    assert interviews[0]["status"] == "CANCELLED"
    assert client.get("/api/notifications").json["data"]["total"] >= 2
