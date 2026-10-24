from io import BytesIO


def test_resume_upload_download_and_ownership(client, register_user):
    register_user(client, "CANDIDATE", "resume-owner@example.test")
    response = client.post("/api/resumes", data={
        "resume": (BytesIO(b"%PDF-1.4 test document"), "resume.pdf", "application/pdf"),
    }, content_type="multipart/form-data")
    assert response.status_code == 201
    resume_id = response.json["data"]["_id"]
    assert client.get(f"/api/resumes/{resume_id}").status_code == 200
    client.post("/api/auth/logout")
    register_user(client, "CANDIDATE", "other-candidate@example.test")
    assert client.get(f"/api/resumes/{resume_id}").status_code == 403


def test_resume_rejects_unsupported_extensions(client, register_user):
    register_user(client, "CANDIDATE", "resume-invalid@example.test")
    response = client.post("/api/resumes", data={
        "resume": (BytesIO(b"not a resume"), "payload.exe", "application/octet-stream"),
    }, content_type="multipart/form-data")
    assert response.status_code == 400
    assert response.json["error_code"] == "RESUME_UPLOAD_ERROR"
