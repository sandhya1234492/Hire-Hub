from pathlib import Path
from datetime import datetime, timezone

from bson import ObjectId
import pytest
from app.repositories.admin_repository import AdminRepository
from app.services.auth_service import AuthService
from scripts.create_indexes import create_indexes
from scripts.seed_data import (
    DEMO_ADMIN_EMAIL,
    DEMO_ADMIN_PASSWORD,
    DEMO_PASSWORD,
    seed,
)


def test_seed_is_idempotent_and_preserves_existing_users(app):
    database = app.config["MONGO_CLIENT"]["hirehub_test"]
    upload_folder = app.config["UPLOAD_FOLDER"]
    existing = AuthService(database).register({
        "name": "Real User",
        "email": "real.person@example.test",
        "password": "real-user-password",
        "role": "CANDIDATE",
    })

    first_counts = seed(database, upload_folder)
    second_counts = seed(database, upload_folder)

    assert first_counts == second_counts == {
        "admins": 1,
        "candidates": 20,
        "recruiters": 10,
        "companies": 5,
        "jobs": 30,
        "applications": 50,
        "interviews": 15,
    }
    assert database["users"].count_documents({"is_demo_data": True}) == 31
    assert database["jobs"].count_documents({"is_demo_data": True}) == 30
    assert database["applications"].count_documents({"is_demo_data": True}) == 50
    assert database["interviews"].count_documents({"is_demo_data": True}) == 15
    assert database["resumes"].count_documents({"is_demo_data": True}) == 20
    assert database["notifications"].count_documents({"is_demo_data": True}) == 60
    assert database["users"].find_one({"_id": existing["_id"]})["name"] == "Real User"
    assert database["users"].find_one({
        "email": "candidate01@demo.hirehub.test",
        "password_hash": DEMO_PASSWORD,
    }) is None
    admin = database["users"].find_one({"email": DEMO_ADMIN_EMAIL, "role": "ADMIN"})
    assert admin["password_hash"] != DEMO_ADMIN_PASSWORD
    assert AuthService(database).authenticate(DEMO_ADMIN_EMAIL, DEMO_ADMIN_PASSWORD)


def test_seed_relationship_integrity_and_status_coverage(app):
    database = app.config["MONGO_CLIENT"]["hirehub_test"]
    seed(database, app.config["UPLOAD_FOLDER"])
    candidate_ids = {
        user["_id"] for user in database["users"].find({"role": "CANDIDATE", "is_demo_data": True})
    }
    recruiter_ids = {
        user["_id"] for user in database["users"].find({"role": "RECRUITER", "is_demo_data": True})
    }
    job_ids = {
        job["_id"] for job in database["jobs"].find({"is_demo_data": True})
    }
    application_ids = {
        application["_id"]
        for application in database["applications"].find({"is_demo_data": True})
    }
    for job in database["jobs"].find({"is_demo_data": True}):
        assert job["recruiter_id"] in recruiter_ids
        assert job["company_id"] in {
            company["_id"] for company in database["companies"].find({"is_demo_data": True})
        }
    statuses = {
        item["_id"]
        for item in database["applications"].aggregate([
            {"$match": {"is_demo_data": True}},
            {"$group": {"_id": "$status"}},
        ])
    }
    assert statuses == {
        "APPLIED", "UNDER_REVIEW", "SHORTLISTED", "INTERVIEW_SCHEDULED",
        "SELECTED", "REJECTED", "WITHDRAWN",
    }
    for application in database["applications"].find({"is_demo_data": True}):
        assert application["candidate_id"] in candidate_ids
        assert application["job_id"] in job_ids
    for interview in database["interviews"].find({"is_demo_data": True}):
        assert interview["application_id"] in application_ids
        application = database["applications"].find_one({"_id": interview["application_id"]})
        assert interview["candidate_id"] == application["candidate_id"]
        job = database["jobs"].find_one({"_id": application["job_id"]})
        assert interview["recruiter_id"] == job["recruiter_id"]


def test_seed_stops_before_writing_when_reserved_email_is_a_real_account(app):
    database = app.config["MONGO_CLIENT"]["hirehub_test"]
    AuthService(database).register({
        "name": "Existing Account",
        "email": "candidate01@demo.hirehub.test",
        "password": "existing-account-password",
        "role": "CANDIDATE",
    })
    with pytest.raises(RuntimeError, match="non-demo accounts"):
        seed(database, app.config["UPLOAD_FOLDER"])
    assert database["companies"].count_documents({"is_demo_data": True}) == 0
    assert database["jobs"].count_documents({"is_demo_data": True}) == 0


def test_demo_login_candidate_recruiter_admin_dashboards_and_counts(app, client):
    database = app.config["MONGO_CLIENT"]["hirehub_test"]
    seed(database, app.config["UPLOAD_FOLDER"])
    create_indexes(database)

    for email, password, expected_role, dashboard_path in (
        ("candidate01@demo.hirehub.test", DEMO_PASSWORD, "CANDIDATE", "/dashboard"),
        ("recruiter01@demo.hirehub.test", DEMO_PASSWORD, "RECRUITER", "/dashboard"),
        (DEMO_ADMIN_EMAIL, DEMO_ADMIN_PASSWORD, "ADMIN", "/admin/dashboard"),
    ):
        response = client.post("/api/auth/login", json={
            "email": email, "password": password,
        })
        assert response.status_code == 200
        assert response.json["data"]["role"] == expected_role
        page = client.get(dashboard_path)
        assert page.status_code == 200
        if expected_role == "CANDIDATE":
            assert b"Profile completion" in page.data
            assert b"Recommended for you" in page.data
            assert b"Notifications" in page.data
            resume = database["resumes"].find_one({
                "candidate_id": ObjectId(response.json["data"]["_id"])
            })
            assert resume and (
                Path(app.config["UPLOAD_FOLDER"]) / resume["stored_name"]
            ).is_file()
        elif expected_role == "RECRUITER":
            assert b"Shortlisted" in page.data
            assert b"Selections" in page.data
            recruiter_id = ObjectId(response.json["data"]["_id"])
            recruiter_job_ids = {
                job["_id"] for job in database["jobs"].find(
                    {"recruiter_id": recruiter_id}, {"_id": 1}
                )
            }
            applications = list(database["applications"].find(
                {"job_id": {"$in": list(recruiter_job_ids)}}
            ))
            assert applications
            assert all(item["job_id"] in recruiter_job_ids for item in applications)
        else:
            assert b"Selections" in page.data
            counts = AdminRepository(database).dashboard_counts()
            assert counts["users"] == 31
            assert counts["candidates"] == 20
            assert counts["recruiters"] == 10
            assert counts["companies"] == 5
            assert counts["jobs"] == 30
            assert counts["applications"] == 50
            assert counts["interviews"] == 15
            assert counts["selections"] > 0
        client.post("/api/auth/logout")


def test_seeded_search_supports_combined_case_insensitive_filters(client, app):
    database = app.config["MONGO_CLIENT"]["hirehub_test"]
    seed(database, app.config["UPLOAD_FOLDER"])
    create_indexes(database)
    response = client.get(
        "/api/jobs?keyword=python&skill=flask&location=bengaluru"
        "&min_salary=45000&max_salary=140000&work_mode=remote"
        "&employment_type=full_time&company=Northstar"
    )
    assert response.status_code == 200
    result = response.json["data"]
    assert result["total"] >= 1
    assert all(job["status"] == "OPEN" for job in result["items"])
    deadlines = [datetime.fromisoformat(job["deadline"]) for job in result["items"]]
    assert all(
        deadline.replace(tzinfo=timezone.utc) >= datetime.now(timezone.utc)
        if deadline.tzinfo is None else deadline >= datetime.now(timezone.utc)
        for deadline in deadlines
    )
    assert any("Python" in job["skills"] for job in result["items"])
    web_page = client.get(
        "/jobs?keyword=python&skill=flask&location=bengaluru"
        "&min_salary=45000&max_salary=140000&work_mode=remote"
        "&employment_type=full_time&company=Northstar"
    )
    assert web_page.status_code == 200
    assert b"Python Backend Engineer" in web_page.data
