from datetime import datetime, timezone

from bson import ObjectId
from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.utils import secure_filename

from app.exceptions import HireHubError, UnauthorizedError, ValidationError
from app.extensions import get_database
from app.repositories.base_repository import BaseRepository
from app.repositories.admin_repository import AdminRepository
from app.repositories.user_repository import UserRepository
from app.services.application_service import ApplicationService
from app.services.admin_service import AdminService
from app.services.auth_service import AuthService
from app.services.company_service import CompanyService
from app.services.interview_service import InterviewService
from app.services.job_service import JobService
from app.services.matching_service import MatchingService
from app.services.report_service import ReportService
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
    payload = {} if data is None else data
    return jsonify(success=True, message=message, data=json_value(payload)), status


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


@api.get("/recruiter/company")
@role_required("RECRUITER")
def get_recruiter_company():
    return success(CompanyService(get_database()).get_for_recruiter(current_user_document()))


@api.put("/recruiter/company")
@role_required("RECRUITER")
def update_recruiter_company():
    company = CompanyService(get_database()).update_for_recruiter(
        request.get_json(silent=True) or {}, current_user_document()
    )
    return success(company, "Company profile updated")


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
    if "name" in changes and (not changes["name"] or len(changes["name"]) > 120):
        raise ValidationError("Enter a name no longer than 120 characters.")
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
    for field, required_fields, numeric_field in (
        ("education", {"degree", "institution", "year"}, "year"),
        ("experience", {"title", "company", "years"}, "years"),
    ):
        if field in data:
            values = data[field]
            if not isinstance(values, list) or any(
                not isinstance(item, dict) or not required_fields.issubset(item)
                or any(not str(item.get(name, "")).strip() for name in required_fields)
                for item in values
            ):
                raise ValidationError(f"{field} must be a list of complete profile entries.")
            normalized = []
            for item in values:
                try:
                    amount = float(item[numeric_field])
                except (TypeError, ValueError) as error:
                    raise ValidationError(
                        f"{field} {numeric_field} must be a number."
                    ) from error
                if amount < 0 or (
                    numeric_field == "year" and not amount.is_integer()
                ):
                    raise ValidationError(f"{field} {numeric_field} is invalid.")
                normalized.append({**item, numeric_field: int(amount) if numeric_field == "year" else amount})
            changes[field] = normalized
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
    interview = InterviewService(get_database()).create(
        request.get_json(silent=True) or {}, current_user_document()
    )
    return success(interview, "Interview scheduled", 201)


@api.put("/interviews/<interview_id>")
@role_required("RECRUITER")
def update_interview(interview_id):
    interview = InterviewService(get_database()).update(
        interview_id, request.get_json(silent=True) or {}, current_user_document()
    )
    return success(interview, "Interview updated")


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
    ResumeService(
        get_database(), current_app.config["UPLOAD_FOLDER"]
    ).delete(resume_id, current_user_document())
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
        candidate_ids = (
            [item["_id"] for item in database["users"].find(
                {"role": "CANDIDATE"}, {"_id": 1}
            )]
            if user["role"] == "ADMIN" else [user["_id"]]
        )
        base = {"candidate_id": {"$in": candidate_ids}}
        data = {
            "total_applications": applications.count_documents(base),
            "shortlisted": applications.count_documents({**base, "status": "SHORTLISTED"}),
            "interviews": database["interviews"].count_documents({
                "candidate_id": {"$in": candidate_ids},
            }),
            "selections": applications.count_documents({**base, "status": "SELECTED"}),
        }
    elif role == "recruiter":
        recruiter_ids = (
            [item["_id"] for item in database["users"].find(
                {"role": "RECRUITER"}, {"_id": 1}
            )]
            if user["role"] == "ADMIN" else [user["_id"]]
        )
        jobs = list(database["jobs"].find(
            {"recruiter_id": {"$in": recruiter_ids}}, {"_id": 1, "status": 1}
        ))
        job_ids = [item["_id"] for item in jobs]
        data = {
            "total_jobs": len(jobs),
            "active_jobs": sum(item["status"] == "OPEN" for item in jobs),
            "applications": database["applications"].count_documents({"job_id": {"$in": job_ids}}),
            "shortlisted": database["applications"].count_documents({
                "job_id": {"$in": job_ids}, "status": "SHORTLISTED",
            }),
            "interviews": database["interviews"].count_documents({
                "recruiter_id": {"$in": recruiter_ids},
            }),
            "selections": database["applications"].count_documents({
                "job_id": {"$in": job_ids}, "status": "SELECTED",
            }),
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
            "selections": database["applications"].count_documents({"status": "SELECTED"}),
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


@api.get("/recommendations")
@role_required("CANDIDATE")
def recommendations():
    user = current_user_document()
    jobs = JobService(get_database()).search({"page": 1, "per_page": 100})["items"]
    applied_ids = {
        str(item["job_id"]) for item in get_database()["applications"].find(
            {"candidate_id": user["_id"]}, {"job_id": 1}
        )
    }
    recommendations = [
        {"job": job, **MatchingService().calculate(user, job)}
        for job in jobs if str(job["_id"]) not in applied_ids
    ]
    recommendations.sort(key=lambda item: item["score"], reverse=True)
    return success(recommendations[:20])


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


@api.get("/admin/dashboard")
@role_required("ADMIN")
def admin_dashboard():
    return success(AdminService(get_database()).analytics())


@api.get("/admin/users")
@role_required("ADMIN")
def admin_users():
    role = str(request.args.get("role", "")).upper() or None
    if role and role not in {"CANDIDATE", "RECRUITER", "ADMIN"}:
        raise ValidationError("Select a valid user role.")
    result = AdminRepository(get_database()).list_users(
        role, page=request.args.get("page", 1)
    )
    return success(result)


@api.patch("/admin/users/<user_id>/active")
@role_required("ADMIN")
def admin_set_user_active(user_id):
    data = request.get_json(silent=True) or {}
    active = data.get("active")
    if not isinstance(active, bool):
        raise ValidationError("active must be a boolean.")
    user = AdminService(get_database()).set_user_active(
        user_id, active, current_user_document()
    )
    return success(user, "User status updated")


@api.get("/admin/companies")
@role_required("ADMIN")
def admin_company_list():
    return success(AdminRepository(get_database()).list_companies(
        page=request.args.get("page", 1)
    ))


@api.patch("/admin/companies/<company_id>/verification")
@role_required("ADMIN")
def admin_company_verification(company_id):
    data = request.get_json(silent=True) or {}
    verified = data.get("verified")
    if not isinstance(verified, bool):
        raise ValidationError("verified must be a boolean.")
    company = AdminService(get_database()).verify_company(
        company_id, verified, current_user_document()
    )
    return success(company, "Company verification updated")


@api.get("/admin/jobs")
@role_required("ADMIN")
def admin_job_list():
    return success(AdminRepository(get_database()).list_jobs(
        page=request.args.get("page", 1)
    ))


@api.patch("/admin/jobs/<job_id>/moderation")
@role_required("ADMIN")
def admin_moderate_job(job_id):
    data = request.get_json(silent=True) or {}
    job = AdminService(get_database()).moderate_job(
        job_id, data.get("status"), current_user_document()
    )
    return success(job, "Job moderation updated")


@api.get("/admin/applications")
@role_required("ADMIN")
def admin_application_list():
    query = {}
    status = str(request.args.get("status", "")).upper()
    if status:
        if status not in ApplicationService.TRANSITIONS:
            raise ValidationError("Select a valid application status.")
        query["status"] = status
    return success(AdminRepository(get_database()).list_applications(
        query, page=request.args.get("page", 1)
    ))


@api.get("/admin/audit-logs")
@role_required("ADMIN")
def admin_audit_logs():
    return success(AdminRepository(get_database()).list_audit_logs(
        page=request.args.get("page", 1)
    ))


@api.get("/admin/reports/<report_type>")
@role_required("ADMIN")
def admin_report(report_type):
    headers, rows = ReportService(get_database()).build(report_type, request.args)
    return success({"headers": headers, "rows": rows})
