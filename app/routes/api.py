from datetime import datetime, timezone

from bson import ObjectId
from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.utils import secure_filename

from app.exceptions import HireHubError, UnauthorizedError, ValidationError
from app.extensions import get_database
from app.repositories.base_repository import BaseRepository
from app.repositories.user_repository import UserRepository
from app.services.application_service import ApplicationService
from app.services.auth_service import AuthService
from app.services.job_service import JobService
from app.services.matching_service import MatchingService
from app.services.notification_service import NotificationService
from app.services.resume_service import ResumeService
from app.utils.auth import current_user_document, login_required, role_required

api = Blueprint("api", __name__)


def json_value(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items() if key != "password_hash"}
    return value


def success(data=None, message="OK", status=200):
    return jsonify(success=True, message=message, data=json_value(data or {})), status


@api.errorhandler(HireHubError)
def handle_domain_error(error):
    return jsonify(
        success=False, message=str(error), error_code=error.error_code
    ), error.status_code


@api.errorhandler(ValidationError)
def handle_validation_error(error):
    return jsonify(success=False, message=str(error), error_code=error.error_code), error.status_code


@api.post("/auth/register")
def register():
    data = request.get_json(silent=True) or request.form
    user = AuthService(get_database()).register(data)
    session.clear()
    session["user_id"] = str(user["_id"])
    session.permanent = True
    return success(user, "Account created successfully", 201)


@api.post("/auth/login")
def login():
    data = request.get_json(silent=True) or request.form
    user = AuthService(get_database()).authenticate(data.get("email"), data.get("password"))
    session.clear()
    session["user_id"] = str(user["_id"])
    session.permanent = True
    return success(user, "Signed in successfully")


@api.post("/auth/logout")
@login_required
def logout():
    user_id = session.get("user_id")
    from app.services.audit_service import AuditService
    AuditService(get_database()).record(user_id, "USER_LOGOUT", "user", user_id)
    session.clear()
    return success(message="Signed out successfully")


@api.get("/auth/me")
@login_required
def me():
    return success(current_user_document())


@api.get("/jobs")
def list_jobs():
    result = JobService(get_database()).search(request.args)
    return success(result)


@api.get("/jobs/<job_id>")
def get_job(job_id):
    job = JobService(get_database()).get(job_id)
    job["company"] = get_database()["companies"].find_one({"_id": job["company_id"]})
    user = current_user_document()
    if user and user.get("role") == "CANDIDATE":
        job["match"] = MatchingService().calculate(user, job)
    return success(job)


@api.post("/jobs")
@role_required("RECRUITER")
def create_job():
    job = JobService(get_database()).create(request.get_json(silent=True) or {}, current_user_document())
    return success(job, "Job created successfully", 201)


@api.put("/jobs/<job_id>")
@role_required("RECRUITER")
def update_job(job_id):
    job = JobService(get_database()).update(
        job_id, request.get_json(silent=True) or {}, current_user_document()
    )
    return success(job, "Job updated successfully")


@api.delete("/jobs/<job_id>")
@role_required("RECRUITER")
def close_job(job_id):
    job = JobService(get_database()).update(job_id, {}, current_user_document(), close=True)
    return success(job, "Job closed successfully")


@api.get("/candidates/<candidate_id>")
@login_required
def get_candidate(candidate_id):
    user = current_user_document()
    if user.get("role") not in {"RECRUITER", "ADMIN"} and str(user["_id"]) != candidate_id:
        raise UnauthorizedError("You can only view your own profile.")
    candidate = UserRepository(get_database()).get_by_id(candidate_id)
    if not candidate or candidate.get("role") != "CANDIDATE":
        from app.exceptions import UserNotFoundError
        raise UserNotFoundError("Candidate not found.")
    return success(candidate)


@api.put("/candidates/<candidate_id>")
@role_required("CANDIDATE")
def update_candidate(candidate_id):
    user = current_user_document()
    if str(user["_id"]) != candidate_id:
        raise UnauthorizedError("You can only update your own profile.")
    data = request.get_json(silent=True) or {}
    changes = {}
    for field in ("name", "phone", "location", "notice_period"):
        if field in data:
            changes[field] = str(data[field]).strip()
    if "skills" in data:
        changes["skills"] = AuthService._skills(data["skills"])
    for field in ("experience_years", "expected_salary"):
        if field in data:
            try:
                value = float(data[field]) if data[field] is not None else None
            except (TypeError, ValueError) as error:
                raise ValidationError(f"{field} must be a number.") from error
            if value is not None and value < 0:
                raise ValidationError(f"{field} cannot be negative.")
            changes[field] = value
    changes["updated_at"] = datetime.now(timezone.utc)
    UserRepository(get_database()).update(user["_id"], changes)
    return success(UserRepository(get_database()).get_by_id(user["_id"]), "Profile updated")


@api.post("/jobs/<job_id>/apply")
@role_required("CANDIDATE")
def apply(job_id):
    application = ApplicationService(get_database()).apply(job_id, current_user_document())
    return success(application, "Application submitted successfully", 201)


@api.get("/applications")
@login_required
def list_applications():
    user = current_user_document()
    query = {}
    if user["role"] == "CANDIDATE":
        query["candidate_id"] = user["_id"]
    elif user["role"] == "RECRUITER":
        jobs = list(get_database()["jobs"].find(
            {"recruiter_id": user["_id"]}, {"_id": 1}
        ))
        query["job_id"] = {"$in": [job["_id"] for job in jobs]}
    result = BaseRepository(get_database(), "applications").list(
        query, page=request.args.get("page", 1), sort=("applied_at", -1)
    )
    return success(result)


@api.get("/applications/<application_id>")
@login_required
def get_application(application_id):
    user = current_user_document()
    application = BaseRepository(get_database(), "applications").get_by_id(application_id)
    if not application:
        from app.exceptions import ApplicationNotFoundError
        raise ApplicationNotFoundError("Application not found.")
    job = BaseRepository(get_database(), "jobs").get_by_id(application["job_id"])
    if user["role"] != "ADMIN" and not (
        user["_id"] == application["candidate_id"]
        or (job and job["recruiter_id"] == user["_id"])
    ):
        raise UnauthorizedError("You cannot access this application.")
    return success(application)


@api.put("/applications/<application_id>/status")
@role_required("RECRUITER")
def update_application_status(application_id):
    data = request.get_json(silent=True) or {}
    application = ApplicationService(get_database()).update_status(
        application_id, data.get("status"), current_user_document(), data.get("recruiter_notes", "")
    )
    return success(application, "Application status updated")


@api.post("/applications/<application_id>/withdraw")
@role_required("CANDIDATE")
def withdraw_application(application_id):
    application = ApplicationService(get_database()).withdraw(
        application_id, current_user_document()
    )
    return success(application, "Application withdrawn")


@api.post("/jobs/<job_id>/save")
@role_required("CANDIDATE")
def save_job(job_id):
    job = JobService(get_database()).get(job_id)
    user = current_user_document()
    saved_jobs = [str(item) for item in user.get("saved_jobs", [])]
    if str(job["_id"]) not in saved_jobs:
        saved_jobs.append(str(job["_id"]))
        UserRepository(get_database()).update(user["_id"], {"saved_jobs": saved_jobs})
    return success({"saved": True, "job_id": str(job["_id"])}, "Job saved")


@api.delete("/jobs/<job_id>/save")
@role_required("CANDIDATE")
def unsave_job(job_id):
    job = JobService(get_database()).get(job_id)
    user = current_user_document()
    saved_jobs = [str(item) for item in user.get("saved_jobs", [])]
    saved_jobs = [item for item in saved_jobs if item != str(job["_id"])]
    UserRepository(get_database()).update(user["_id"], {"saved_jobs": saved_jobs})
    return success({"saved": False, "job_id": str(job["_id"])}, "Saved job removed")


@api.post("/interviews")
@role_required("RECRUITER")
def create_interview():
    user = current_user_document()
    data = request.get_json(silent=True) or {}
    application = BaseRepository(get_database(), "applications").get_by_id(
        data.get("application_id")
    )
    if not application:
        from app.exceptions import ApplicationNotFoundError
        raise ApplicationNotFoundError("Application not found.")
    job = BaseRepository(get_database(), "jobs").get_by_id(application["job_id"])
    if not job or job["recruiter_id"] != user["_id"]:
        raise UnauthorizedError("You can only schedule interviews for your jobs.")
    interview_type = str(data.get("type", "ONLINE")).upper()
    if interview_type not in {"ONLINE", "PHONE", "IN_PERSON"}:
        raise ValidationError("Select a valid interview type.")
    date_value = str(data.get("date", ""))
    time_value = str(data.get("time", ""))
    if not date_value or not time_value:
        raise ValidationError("Interview date and time are required.")
    if application["status"] not in {"SHORTLISTED", "INTERVIEW_SCHEDULED"}:
        from app.exceptions import InvalidApplicationStatusError
        raise InvalidApplicationStatusError("Only shortlisted candidates can be scheduled.")
    interview = {
        "application_id": application["_id"], "candidate_id": application["candidate_id"],
        "recruiter_id": user["_id"], "date": date_value, "time": time_value,
        "type": interview_type, "meeting_link": str(data.get("meeting_link", "")).strip(),
        "status": "SCHEDULED", "feedback": "",
        "created_at": datetime.now(timezone.utc),
    }
    interview_id = get_database()["interviews"].insert_one(interview).inserted_id
    get_database()["applications"].update_one(
        {"_id": application["_id"]},
        {"$set": {"status": "INTERVIEW_SCHEDULED", "interview_id": interview_id,
                  "updated_at": datetime.now(timezone.utc)}},
    )
    NotificationService(get_database()).create(
        application["candidate_id"], f"An interview is scheduled for {date_value} at {time_value}.",
        "INTERVIEW",
    )
    return success({"_id": interview_id, **interview}, "Interview scheduled", 201)


@api.put("/interviews/<interview_id>")
@role_required("RECRUITER")
def update_interview(interview_id):
    user = current_user_document()
    repo = BaseRepository(get_database(), "interviews")
    interview = repo.get_by_id(interview_id)
    if not interview:
        from app.exceptions import UserNotFoundError
        raise UserNotFoundError("Interview not found.")
    if interview["recruiter_id"] != user["_id"]:
        raise UnauthorizedError("You can only manage your own interviews.")
    data = request.get_json(silent=True) or {}
    changes = {}
    if "status" in data:
        status = str(data["status"]).upper()
        if status not in {"SCHEDULED", "COMPLETED", "CANCELLED"}:
            raise ValidationError("Select a valid interview status.")
        changes["status"] = status
    for field in ("date", "time", "meeting_link", "feedback"):
        if field in data:
            changes[field] = str(data[field]).strip()
    if not changes:
        raise ValidationError("Provide at least one interview field to update.")
    repo.update(interview["_id"], changes)
    if changes.get("status") == "CANCELLED":
        NotificationService(get_database()).create(
            interview["candidate_id"], "Your interview was cancelled.", "INTERVIEW"
        )
    return success(repo.get_by_id(interview["_id"]), "Interview updated")


@api.get("/interviews")
@login_required
def list_interviews():
    user = current_user_document()
    query = {}
    if user["role"] == "CANDIDATE":
        query["candidate_id"] = user["_id"]
    elif user["role"] == "RECRUITER":
        query["recruiter_id"] = user["_id"]
    result = BaseRepository(get_database(), "interviews").list(
        query, page=request.args.get("page", 1), sort=("date", 1)
    )
    return success(result)


@api.post("/resumes")
@role_required("CANDIDATE")
def upload_resume():
    metadata = ResumeService(
        get_database(), current_app.config["UPLOAD_FOLDER"]
    ).upload(request.files.get("resume"), current_user_document())
    return success(metadata, "Resume uploaded", 201)


@api.get("/resumes/<resume_id>")
@login_required
def download_resume(resume_id):
    from flask import abort, send_from_directory
    from bson import ObjectId
    from bson.errors import InvalidId
    try:
        resume = get_database()["resumes"].find_one({"_id": ObjectId(resume_id)})
    except (InvalidId, TypeError):
        resume = None
    if not resume:
        from app.exceptions import UserNotFoundError
        raise UserNotFoundError("Resume not found.")
    user = current_user_document()
    if user["role"] == "RECRUITER":
        job_ids = [item["_id"] for item in get_database()["jobs"].find(
            {"recruiter_id": user["_id"]}, {"_id": 1}
        )]
        authorized = get_database()["applications"].find_one({
            "candidate_id": resume["candidate_id"], "job_id": {"$in": job_ids},
        })
        if not authorized:
            raise UnauthorizedError("You can only access resumes for candidates who applied to your jobs.")
    elif user["role"] != "ADMIN" and user["_id"] != resume["candidate_id"]:
        raise UnauthorizedError("You cannot access this resume.")
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"], resume["stored_name"],
        as_attachment=True, download_name=secure_filename(resume["filename"]),
        mimetype=resume["content_type"],
    )


@api.delete("/resumes/<resume_id>")
@role_required("CANDIDATE")
def delete_resume(resume_id):
    from bson import ObjectId
    from bson.errors import InvalidId
    from pathlib import Path
    try:
        object_id = ObjectId(resume_id)
    except (InvalidId, TypeError):
        object_id = None
    resume = get_database()["resumes"].find_one({"_id": object_id}) if object_id else None
    user = current_user_document()
    if not resume or resume["candidate_id"] != user["_id"]:
        raise UnauthorizedError("Resume not found or access denied.")
    path = Path(current_app.config["UPLOAD_FOLDER"]) / resume["stored_name"]
    if path.is_file():
        path.unlink()
    get_database()["resumes"].delete_one({"_id": resume["_id"]})
    return success(message="Resume deleted")


@api.get("/analytics/<role>")
@role_required("CANDIDATE", "RECRUITER", "ADMIN")
def analytics(role):
    user = current_user_document()
    role = role.lower()
    if role not in {"candidate", "recruiter", "admin"} or (
        user["role"] != "ADMIN" and user["role"].lower() != role
    ):
        raise UnauthorizedError("You cannot view these analytics.")
    database = get_database()
    if role == "candidate":
        applications = database["applications"]
        base = {"candidate_id": user["_id"]}
        data = {
            "total_applications": applications.count_documents(base),
            "shortlisted": applications.count_documents({**base, "status": "SHORTLISTED"}),
            "interviews": applications.count_documents({**base, "status": "INTERVIEW_SCHEDULED"}),
            "selections": applications.count_documents({**base, "status": "SELECTED"}),
        }
    elif role == "recruiter":
        jobs = list(database["jobs"].find({"recruiter_id": user["_id"]}, {"_id": 1, "status": 1}))
        job_ids = [item["_id"] for item in jobs]
        data = {
            "total_jobs": len(jobs),
            "active_jobs": sum(item["status"] == "OPEN" for item in jobs),
            "applications": database["applications"].count_documents({"job_id": {"$in": job_ids}}),
        }
    else:
        data = {
            "users": database["users"].count_documents({}),
            "candidates": database["users"].count_documents({"role": "CANDIDATE"}),
            "recruiters": database["users"].count_documents({"role": "RECRUITER"}),
            "companies": database["companies"].count_documents({}),
            "jobs": database["jobs"].count_documents({}),
            "applications": database["applications"].count_documents({}),
            "interviews": database["interviews"].count_documents({}),
        }
    return success(data)


@api.get("/notifications")
@login_required
def list_notifications():
    user = current_user_document()
    result = BaseRepository(get_database(), "notifications").list(
        {"user_id": user["_id"]}, page=request.args.get("page", 1), sort=("created_at", -1)
    )
    return success(result)


@api.post("/notifications/<notification_id>/read")
@login_required
def mark_notification_read(notification_id):
    user = current_user_document()
    repo = BaseRepository(get_database(), "notifications")
    notification = repo.get_by_id(notification_id)
    if not notification or notification["user_id"] != user["_id"]:
        raise UnauthorizedError("Notification not found or access denied.")
    repo.update(notification["_id"], {"read": True})
    return success(message="Notification marked as read")
