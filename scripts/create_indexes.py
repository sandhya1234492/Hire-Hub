import sys
from pathlib import Path

from pymongo import ASCENDING, DESCENDING, TEXT

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.extensions import get_database


def create_indexes(database):
    database["users"].create_index([("email", ASCENDING)], unique=True)
    database["jobs"].create_index([("title", TEXT), ("description", TEXT)])
    database["jobs"].create_index([("skills", ASCENDING)])
    database["jobs"].create_index([("location", ASCENDING), ("work_mode", ASCENDING)])
    database["jobs"].create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    database["jobs"].create_index([("company_id", ASCENDING), ("status", ASCENDING)])
    database["jobs"].create_index([("recruiter_id", ASCENDING), ("created_at", DESCENDING)])
    database["jobs"].create_index([("deadline", ASCENDING)])
    database["jobs"].create_index([("salary_min", ASCENDING), ("salary_max", ASCENDING)])
    database["jobs"].create_index([("experience_min", ASCENDING)])
    database["applications"].create_index(
        [("candidate_id", ASCENDING), ("job_id", ASCENDING)], unique=True
    )
    database["applications"].create_index([("job_id", ASCENDING), ("status", ASCENDING)])
    database["applications"].create_index([("candidate_id", ASCENDING), ("applied_at", DESCENDING)])
    database["interviews"].create_index([("candidate_id", ASCENDING), ("date", ASCENDING)])
    database["interviews"].create_index([("recruiter_id", ASCENDING), ("date", ASCENDING)])
    database["notifications"].create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    database["resumes"].create_index([("candidate_id", ASCENDING)], unique=True)


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        create_indexes(get_database())
    print("HireHub indexes created.")
