import secrets
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import get_database

NAMES = [
    "Avery Morgan", "Jordan Lee", "Riley Patel", "Taylor Chen", "Casey Brooks",
    "Morgan Diaz", "Jamie Kim", "Alex Rivera", "Cameron Shah", "Reese Parker",
    "Quinn Bailey", "Drew Singh", "Skyler James", "Rowan Clark", "Emerson Reed",
    "Finley Young", "Kendall Ward", "Payton Ross", "Sage Cooper", "Robin Bell",
]
SKILLS = ["Python", "SQL", "MongoDB", "JavaScript", "React", "Flask", "AWS", "Docker"]
LOCATIONS = ["Bengaluru", "Hyderabad", "Mumbai", "Pune", "Remote"]
COMPANIES = ["Northstar Labs", "BrightPath Systems", "Fieldstone Digital", "Orbit Works", "Juniper Cloud"]


def seed(database):
    collections = [
        "users", "candidates", "recruiters", "companies", "jobs",
        "applications", "interviews", "resumes", "notifications", "audit_logs",
    ]
    if any(database[name].count_documents({}) for name in collections):
        raise RuntimeError("Seed only into an empty HireHub database; no data was changed.")

    now = datetime.now(timezone.utc)
    companies = [
        {"name": name, "location": LOCATIONS[index], "description": f"{name} builds useful products.",
         "verified": index < 3, "created_at": now}
        for index, name in enumerate(COMPANIES)
    ]
    company_ids = [database["companies"].insert_one(item).inserted_id for item in companies]
    candidate_ids = []
    recruiter_ids = []
    for index, name in enumerate(NAMES):
        email = f"candidate{index + 1}@example.test"
        user = {
            "name": name, "email": email, "phone": f"+1-555-010{index:02d}",
            "role": "CANDIDATE", "password_hash": generate_password_hash(secrets.token_urlsafe(20)),
            "is_active": True, "location": LOCATIONS[index % len(LOCATIONS)],
            "skills": SKILLS[index % 5:index % 5 + 3], "experience_years": index % 9,
            "saved_jobs": [], "created_at": now - timedelta(days=index * 4),
        }
        candidate_ids.append(database["users"].insert_one(user).inserted_id)
        database["candidates"].insert_one({"user_id": candidate_ids[-1], "created_at": now})

    for index in range(10):
        email = f"recruiter{index + 1}@example.test"
        company_id = company_ids[index % len(company_ids)]
        user = {
            "name": f"Recruiter {index + 1}", "email": email, "phone": "",
            "role": "RECRUITER", "company_id": company_id,
            "password_hash": generate_password_hash(secrets.token_urlsafe(20)),
            "is_active": True, "created_at": now - timedelta(days=index * 6),
        }
        recruiter_ids.append(database["users"].insert_one(user).inserted_id)
        database["recruiters"].insert_one({
            "user_id": recruiter_ids[-1], "company_id": company_id, "created_at": now,
        })

    job_ids = []
    for index in range(30):
        job = {
            "title": f"{['Software Engineer', 'Data Analyst', 'Product Designer'][index % 3]} {index + 1}",
            "description": "Join a collaborative team working on practical, high-impact products.",
            "company_id": company_ids[index % len(company_ids)],
            "recruiter_id": recruiter_ids[index % len(recruiter_ids)],
            "skills": SKILLS[index % 5:index % 5 + 3],
            "location": LOCATIONS[index % len(LOCATIONS)],
            "work_mode": ["REMOTE", "HYBRID", "ONSITE"][index % 3],
            "employment_type": ["FULL_TIME", "PART_TIME", "INTERNSHIP", "CONTRACT"][index % 4],
            "experience_min": index % 4, "experience_max": (index % 4) + 4,
            "salary_min": 50000 + (index % 5) * 10000,
            "salary_max": 90000 + (index % 5) * 10000,
            "status": "OPEN", "posted_date": now, "created_at": now, "updated_at": now,
        }
        job_ids.append(database["jobs"].insert_one(job).inserted_id)

    statuses = ["APPLIED", "UNDER_REVIEW", "SHORTLISTED", "REJECTED", "SELECTED"]
    for index in range(50):
        database["applications"].insert_one({
            "candidate_id": candidate_ids[index % len(candidate_ids)],
            "job_id": job_ids[index % len(job_ids)],
            "status": statuses[index % len(statuses)],
            "applied_at": now - timedelta(days=index),
            "updated_at": now - timedelta(days=index),
            "recruiter_notes": "",
        })
    applications = list(database["applications"].find().limit(15))
    for index, application in enumerate(applications):
        database["interviews"].insert_one({
            "application_id": application["_id"],
            "candidate_id": application["candidate_id"],
            "recruiter_id": database["jobs"].find_one(
                {"_id": application["job_id"]}, {"recruiter_id": 1}
            )["recruiter_id"],
            "date": (now + timedelta(days=index + 1)).date().isoformat(),
            "time": "10:00", "type": "ONLINE", "meeting_link": "",
            "status": "SCHEDULED", "feedback": "",
        })


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        seed(get_database())
    print("Inserted 20 candidates, 10 recruiters, 5 companies, 30 jobs, 50 applications and 15 interviews.")
