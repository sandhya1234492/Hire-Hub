"""Idempotently add fictional HireHub demo records without deleting real data."""

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from werkzeug.security import generate_password_hash

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.config import Config
from app.exceptions import UserAlreadyExistsError
from app.extensions import get_database
from app.repositories.base_repository import BaseRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService

DEMO_PASSWORD = "HireHubDemo2026!"
DEMO_ADMIN_NAME = "HireHub Demo Administrator"
DEMO_ADMIN_EMAIL = "admin@demo.hirehub.test"
DEMO_ADMIN_PASSWORD = "HireHubAdmin2026!"

PEOPLE = [
    ("Avery Morgan", "Bengaluru", ["Python", "Flask", "MongoDB"], 4),
    ("Jordan Lee", "Hyderabad", ["Java", "Spring Boot", "SQL"], 6),
    ("Riley Patel", "Mumbai", ["JavaScript", "React", "Node.js"], 3),
    ("Taylor Chen", "Pune", ["Python", "SQL", "Data Analysis"], 5),
    ("Casey Brooks", "Delhi", ["Java", "AWS", "Docker"], 7),
    ("Morgan Diaz", "Chennai", ["HTML", "CSS", "JavaScript"], 2),
    ("Jamie Kim", "Remote", ["Python", "Django", "PostgreSQL"], 8),
    ("Alex Rivera", "Bengaluru", ["React", "TypeScript", "Node.js"], 4),
    ("Cameron Shah", "Hyderabad", ["SQL", "Power BI", "Excel"], 3),
    ("Reese Parker", "Pune", ["C#", ".NET", "Azure"], 9),
    ("Quinn Bailey", "Mumbai", ["Java", "Kotlin", "SQL"], 5),
    ("Drew Singh", "Delhi", ["Python", "Machine Learning", "SQL"], 6),
    ("Skyler James", "Chennai", ["PHP", "Laravel", "MySQL"], 4),
    ("Rowan Clark", "Remote", ["JavaScript", "Vue.js", "CSS"], 3),
    ("Emerson Reed", "Bengaluru", ["Go", "Kubernetes", "AWS"], 7),
    ("Finley Young", "Hyderabad", ["Python", "FastAPI", "PostgreSQL"], 2),
    ("Kendall Ward", "Pune", ["Java", "Spring Boot", "Docker"], 8),
    ("Payton Ross", "Mumbai", ["HTML", "CSS", "React"], 1),
    ("Sage Cooper", "Delhi", ["SQL", "Tableau", "Data Analysis"], 5),
    ("Robin Bell", "Remote", ["Ruby", "Rails", "PostgreSQL"], 6),
]

COMPANIES = [
    ("Northstar Labs Demo", "Bengaluru", "Cloud tools for modern engineering teams."),
    ("BrightPath Systems Demo", "Hyderabad", "Data products for growing businesses."),
    ("Fieldstone Digital Demo", "Mumbai", "Customer-focused web and mobile platforms."),
    ("Orbit Works Demo", "Pune", "Reliable software for distributed operations."),
    ("Juniper Cloud Demo", "Remote", "Infrastructure and developer productivity tools."),
]

JOB_SPECS = [
    ("Python Backend Engineer", ["Python", "Flask", "MongoDB"]),
    ("Java Software Engineer", ["Java", "Spring Boot", "SQL"]),
    ("Web Developer", ["HTML", "CSS", "JavaScript"]),
    ("Full Stack Developer", ["React", "Node.js", "JavaScript"]),
    ("Data Analyst", ["SQL", "Python", "Power BI"]),
    ("SQL Database Developer", ["SQL", "PostgreSQL", "Database Design"]),
    ("JavaScript Frontend Engineer", ["JavaScript", "React", "TypeScript"]),
    ("Cloud Platform Engineer", ["AWS", "Docker", "Kubernetes"]),
    ("Data Engineer", ["Python", "SQL", "ETL"]),
    ("QA Automation Engineer", ["Python", "Selenium", "Java"]),
]

LOCATIONS = ["Bengaluru", "Hyderabad", "Mumbai", "Pune", "Delhi", "Remote"]
WORK_MODES = ["REMOTE", "HYBRID", "ONSITE"]
EMPLOYMENT_TYPES = ["FULL_TIME", "PART_TIME", "INTERNSHIP", "CONTRACT"]
APPLICATION_STATUSES = [
    "APPLIED", "UNDER_REVIEW", "SHORTLISTED", "SELECTED", "REJECTED", "WITHDRAWN",
]


def _demo_upsert(collection, key, document):
    collection.update_one(
        {"demo_key": key},
        {"$set": {**document, "demo_key": key, "is_demo_data": True}},
        upsert=True,
    )
    return collection.find_one({"demo_key": key})


def _demo_password_hash(user, password):
    if user and user.get("is_demo_data"):
        return user["password_hash"]
    return generate_password_hash(password)


def _preflight(database):
    candidate_emails = [
        f"candidate{index:02d}@demo.hirehub.test" for index in range(1, 21)
    ]
    recruiter_emails = [
        f"recruiter{index:02d}@demo.hirehub.test" for index in range(1, 11)
    ]
    emails = [
        *candidate_emails,
        *recruiter_emails,
        DEMO_ADMIN_EMAIL,
    ]
    conflicts = [
        user["email"]
        for user in database["users"].find({"email": {"$in": emails}})
        if not user.get("is_demo_data")
    ]
    if conflicts:
        raise RuntimeError(
            "Demo email(s) are already used by non-demo accounts; no data was changed: "
            + ", ".join(conflicts)
        )
    for collection_name, reserved_emails in (
        ("candidates", candidate_emails), ("recruiters", recruiter_emails),
    ):
        orphaned_profiles = [
            profile.get("user_email", "")
            for profile in database[collection_name].find(
                {"user_email": {"$in": reserved_emails}}
            )
            if not profile.get("is_demo_data")
        ]
        if orphaned_profiles:
            raise RuntimeError(
                f"Reserved demo {collection_name} profile(s) conflict with existing "
                f"records; no data was changed: {', '.join(orphaned_profiles)}"
            )
    company_conflicts = [
        company["name"]
        for company in database["companies"].find(
            {"name": {"$in": [item[0] for item in COMPANIES]}}
        )
        if not company.get("is_demo_data")
    ]
    if company_conflicts:
        raise RuntimeError(
            "Demo company name(s) conflict with non-demo records; no data was changed: "
            + ", ".join(company_conflicts)
        )


def _write_demo_resume(path, name, skills):
    paragraphs = [
        f"Demo resume - {name}",
        "Fictional candidate profile for local HireHub testing.",
        f"Skills: {', '.join(skills)}",
        "This document contains sample data only.",
    ]
    paragraph_xml = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{line}</w:t></w:r></w:p>'
        for line in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraph_xml}<w:sectPr/></w:body></w:document>"
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>"
        ))
        docx.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>"
        ))
        docx.writestr("word/document.xml", document)


def seed(database, upload_folder=None):
    """Seed stable demo records; repeated calls update only records marked as demo."""
    _preflight(database)
    now = datetime.now(timezone.utc)

    companies = []
    for index, (name, location, description) in enumerate(COMPANIES):
        companies.append(_demo_upsert(database["companies"], f"company-{index + 1}", {
            "name": name,
            "location": location,
            "description": description,
            "website": f"https://company{index + 1}.example.test",
            "verified": index < 3,
            "created_at": now - timedelta(days=180 - index * 20),
        }))
    company_ids = [company["_id"] for company in companies]

    auth = AuthService(database)
    candidates = []
    for index, (name, location, skills, years) in enumerate(PEOPLE):
        number = index + 1
        email = f"candidate{number:02d}@demo.hirehub.test"
        key = f"candidate-{number:02d}"
        user = UserRepository(database).get_by_email(email)
        is_new_user = user is None
        if not user:
            try:
                user = auth.register({
                    "name": name,
                    "email": email,
                    "phone": f"+1-555-010-{number:04d}",
                    "password": DEMO_PASSWORD,
                    "confirm_password": DEMO_PASSWORD,
                    "role": "CANDIDATE",
                    "location": location,
                    "skills": skills,
                })
            except UserAlreadyExistsError as error:
                raise RuntimeError(f"Unable to create demo candidate {email}.") from error
            user["is_demo_data"] = True
        user_id = user["_id"]
        user_fields = {
            "name": name,
            "phone": f"+1-555-010-{number:04d}",
            "role": "CANDIDATE",
            "password_hash": (
                user["password_hash"] if is_new_user
                else _demo_password_hash(user, DEMO_PASSWORD)
            ),
            "is_active": True,
            "location": location,
            "skills": skills,
            "education": [{
                "degree": ["BSc Computer Science", "BTech Information Technology",
                           "MSc Data Science"][index % 3],
                "institution": f"{['Lakeside', 'Summit', 'Riverside'][index % 3]} University",
                "year": 2016 + index % 8,
            }],
            "experience": [{
                "title": f"{['Software Developer', 'Data Analyst', 'Web Engineer'][index % 3]}",
                "company": f"{COMPANIES[index % len(COMPANIES)][0]}",
                "years": years,
            }],
            "experience_years": years,
            "expected_salary": 65000 + (index % 7) * 12000,
            "notice_period": ["Immediate", "2 weeks", "30 days", "60 days"][index % 4],
            "saved_jobs": [],
            "created_at": now - timedelta(days=220 - index * 5),
            "updated_at": now,
            "demo_key": key,
            "is_demo_data": True,
        }
        database["users"].update_one({"_id": user_id}, {"$set": user_fields})
        candidate_profile = database["candidates"].find_one({"user_email": email})
        if candidate_profile:
            database["candidates"].update_one(
                {"_id": candidate_profile["_id"]},
                {"$set": {"user_id": user_id, "demo_key": key, "is_demo_data": True}},
            )
        else:
            _demo_upsert(database["candidates"], key, {"user_id": user_id})
        candidates.append(database["users"].find_one({"_id": user_id}))

    recruiters = []
    for index in range(10):
        number = index + 1
        email = f"recruiter{number:02d}@demo.hirehub.test"
        key = f"recruiter-{number:02d}"
        company_id = company_ids[index % len(company_ids)]
        user = UserRepository(database).get_by_email(email)
        is_new_user = user is None
        if not user:
            user = auth.register({
                "name": f"{['Harper', 'Logan', 'Parker', 'Dakota', 'Shiloh'][index % 5]} "
                        f"{['Reed', 'Morgan'][index % 2]}",
                "email": email,
                "phone": f"+1-555-020-{number:04d}",
                "password": DEMO_PASSWORD,
                "confirm_password": DEMO_PASSWORD,
                "role": "RECRUITER",
                "company_name": COMPANIES[index % len(COMPANIES)][0],
            })
            user["is_demo_data"] = True
        database["users"].update_one({"_id": user["_id"]}, {"$set": {
            "name": f"{['Harper', 'Logan', 'Parker', 'Dakota', 'Shiloh'][index % 5]} "
                    f"{['Reed', 'Morgan'][index % 2]}",
            "role": "RECRUITER",
            "company_id": company_id,
            "password_hash": (
                user["password_hash"] if is_new_user
                else _demo_password_hash(user, DEMO_PASSWORD)
            ),
            "is_active": True,
            "created_at": now - timedelta(days=170 - index * 7),
            "demo_key": key,
            "is_demo_data": True,
        }})
        recruiter_profile = database["recruiters"].find_one({"user_email": email})
        if recruiter_profile:
            database["recruiters"].update_one({"_id": recruiter_profile["_id"]}, {"$set": {
                "user_id": user["_id"], "company_id": company_id,
                "demo_key": key, "is_demo_data": True,
            }})
        else:
            _demo_upsert(database["recruiters"], key, {
                "user_id": user["_id"], "company_id": company_id, "user_email": email,
            })
        recruiters.append(database["users"].find_one({"_id": user["_id"]}))

    admin_key = "admin-demo"
    admin = UserRepository(database).get_by_email(DEMO_ADMIN_EMAIL)
    admin_document = {
        "name": DEMO_ADMIN_NAME,
        "email": DEMO_ADMIN_EMAIL,
        "phone": "",
        "role": "ADMIN",
        "password_hash": _demo_password_hash(admin, DEMO_ADMIN_PASSWORD),
        "is_active": True,
        "created_at": now,
    }
    admin_document["password_hash"] = (
        _demo_password_hash(admin, DEMO_ADMIN_PASSWORD)
        if admin else generate_password_hash(DEMO_ADMIN_PASSWORD)
    )
    if admin:
        database["users"].update_one(
            {"_id": admin["_id"]},
            {"$set": {
                **admin_document, "demo_key": admin_key, "is_demo_data": True,
            }},
        )
        admin_id = admin["_id"]
    else:
        admin_document.update({"demo_key": admin_key, "is_demo_data": True})
        admin_id = database["users"].insert_one(admin_document).inserted_id
    _demo_upsert(database["audit_logs"], "admin-created", {
        "user_id": admin_id,
        "action": "ADMIN_CREATED",
        "resource": "user",
        "resource_id": admin_id,
        "timestamp": now,
        "metadata": {"source": "development_demo_seed"},
    })

    jobs = []
    for index in range(30):
        role_title, skills = JOB_SPECS[index % len(JOB_SPECS)]
        job_number = index + 1
        status = "OPEN" if index < 22 else ("CLOSED" if index < 27 else "EXPIRED")
        deadline = (
            now + timedelta(days=30 + index % 45)
            if status == "OPEN"
            else now - timedelta(days=3 + index % 14)
        )
        recruiter = recruiters[index % len(recruiters)]
        document = {
            "title": role_title if job_number <= 10 else f"{role_title} - {LOCATIONS[index % len(LOCATIONS)]}",
            "description": (
                f"Join {COMPANIES[index % len(COMPANIES)][0]} as a {role_title}. "
                f"Work with a collaborative team to build and improve production systems. "
                f"Bring experience with {', '.join(skills)} and a thoughtful approach to "
                "testing, communication, and reliable delivery."
            ),
            "company_id": company_ids[index % len(company_ids)],
            "recruiter_id": recruiter["_id"],
            "skills": skills,
            "location": LOCATIONS[index % len(LOCATIONS)],
            "work_mode": WORK_MODES[index % len(WORK_MODES)],
            "employment_type": EMPLOYMENT_TYPES[index % len(EMPLOYMENT_TYPES)],
            "experience_min": index % 5,
            "experience_max": index % 5 + 4,
            "salary_min": 45000 + (index % 8) * 10000,
            "salary_max": 80000 + (index % 8) * 15000,
            "status": status,
            "posted_date": now - timedelta(days=index % 60),
            "deadline": deadline,
            "created_at": now - timedelta(days=index % 60),
            "updated_at": now,
        }
        jobs.append(_demo_upsert(database["jobs"], f"job-{job_number:02d}", document))

    # Keep each candidate/job pair unique while distributing applications across recruiters.
    applications = []
    non_interview_statuses = APPLICATION_STATUSES
    for index in range(50):
        candidate = candidates[index % len(candidates)]
        job = jobs[(index * 7 + index // len(candidates)) % len(jobs)]
        status = (
            "INTERVIEW_SCHEDULED" if index < 15
            else non_interview_statuses[(index - 15) % len(non_interview_statuses)]
        )
        applied_at = now - timedelta(days=50 - index)
        application = _demo_upsert(database["applications"], f"application-{index + 1:02d}", {
            "candidate_id": candidate["_id"],
            "job_id": job["_id"],
            "status": status,
            "applied_at": applied_at,
            "updated_at": applied_at,
            "recruiter_notes": (
                "Demo application reviewed by the hiring team."
                if status in {"SHORTLISTED", "SELECTED", "REJECTED"} else ""
            ),
        })
        applications.append(application)

    interviews = []
    interview_types = ["ONLINE", "PHONE", "IN_PERSON"]
    for index, application in enumerate(applications[:15]):
        job = BaseRepository(database, "jobs").get_by_id(application["job_id"])
        status = ["SCHEDULED", "COMPLETED", "SCHEDULED", "CANCELLED", "COMPLETED"][index % 5]
        date = (
            now + timedelta(days=2 + index)
            if status == "SCHEDULED"
            else now - timedelta(days=2 + index)
        ).date().isoformat()
        interview = _demo_upsert(database["interviews"], f"interview-{index + 1:02d}", {
            "application_id": application["_id"],
            "candidate_id": application["candidate_id"],
            "recruiter_id": job["recruiter_id"],
            "date": date,
            "time": f"{9 + index % 8:02d}:30",
            "type": interview_types[index % len(interview_types)],
            "meeting_link": (
                f"https://meet.example.test/demo-interview-{index + 1:02d}"
                if interview_types[index % len(interview_types)] == "ONLINE" else ""
            ),
            "status": status,
            "feedback": "Demo interview completed." if status == "COMPLETED" else "",
        })
        database["applications"].update_one(
            {"_id": application["_id"]},
            {"$set": {"interview_id": interview["_id"]}},
        )
        interviews.append(interview)

    for index, candidate in enumerate(candidates):
        saved_jobs = [
            str(jobs[(index * 3 + offset * 7) % len(jobs)]["_id"])
            for offset in range(3)
        ]
        database["users"].update_one(
            {"_id": candidate["_id"]}, {"$set": {"saved_jobs": saved_jobs}}
        )

    resume_folder = Path(upload_folder or Config.UPLOAD_FOLDER)
    resume_folder.mkdir(parents=True, exist_ok=True)
    for index, candidate in enumerate(candidates):
        existing_resume = database["resumes"].find_one({
            "candidate_id": candidate["_id"],
        })
        if existing_resume and not existing_resume.get("is_demo_data"):
            continue
        stored_name = f"demo-candidate-{index + 1:02d}.docx"
        path = resume_folder / stored_name
        _write_demo_resume(path, candidate["name"], candidate.get("skills", []))
        _demo_upsert(database["resumes"], f"resume-{index + 1:02d}", {
            "candidate_id": candidate["_id"],
            "filename": f"{candidate['name']} - demo resume.docx",
            "stored_name": stored_name,
            "content_type": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            "size": path.stat().st_size,
        })

    notification_records = [
        (candidate, "APPLICATION_UPDATE", "Your demo application has been received.")
        for candidate in candidates
    ]
    notification_records.extend(
        (recruiter, "NEW_APPLICANT", "A candidate applied to one of your demo roles.")
        for recruiter in recruiters
    )
    for index, (user, category, message) in enumerate(notification_records):
        _demo_upsert(database["notifications"], f"notification-{index + 1:02d}", {
            "user_id": user["_id"],
            "category": category,
            "message": message,
            "read": index % 4 == 0,
            "created_at": now - timedelta(days=index % 20),
        })

    # AuthService creates these records when demo users are first registered.
    database["notifications"].update_many(
        {"user_id": {"$in": [user["_id"] for user in [*candidates, *recruiters]]},
         "category": "REGISTRATION"},
        {"$set": {"is_demo_data": True}},
    )
    database["audit_logs"].update_many(
        {"user_id": {"$in": [user["_id"] for user in [*candidates, *recruiters]]},
         "action": "USER_REGISTERED"},
        {"$set": {"is_demo_data": True}},
    )

    return {
        "admins": 1,
        "candidates": len(candidates),
        "recruiters": len(recruiters),
        "companies": len(companies),
        "jobs": len(jobs),
        "applications": len(applications),
        "interviews": len(interviews),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    app = create_app()
    with app.app_context():
        counts = seed(get_database(), app.config["UPLOAD_FOLDER"])
    print("Demo records are ready (rerunning is safe; real records are preserved):")
    for collection, count in counts.items():
        print(f"  {collection}: {count}")
    print(f"Demo candidate/recruiter login password: {DEMO_PASSWORD}")
    print("Candidate: candidate01@demo.hirehub.test")
    print("Recruiter: recruiter01@demo.hirehub.test")
    print(f"Development-only demo admin: {DEMO_ADMIN_EMAIL} / {DEMO_ADMIN_PASSWORD}")
    print(f"Resume metadata: {counts['candidates']} fictional candidate resumes")
    print("Never use these fixed demo credentials in a production deployment.")


if __name__ == "__main__":
    main()
