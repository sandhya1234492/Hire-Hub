import csv
import io
from datetime import date
from urllib.parse import urlsplit

from flask import (
    Blueprint, Response, abort, current_app, flash, redirect, render_template,
    request, send_from_directory, session, url_for,
)
from werkzeug.utils import secure_filename

from app.exceptions import HireHubError, UnauthorizedError, ValidationError
from app.extensions import get_database
from app.repositories.application_repository import ApplicationRepository
from app.repositories.admin_repository import AdminRepository
from app.repositories.base_repository import BaseRepository
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

web = Blueprint("web", __name__)


@web.app_errorhandler(HireHubError)
def handle_domain_error(error):
    return render_template("errors/error.html", message=str(error)), error.status_code


@web.get("/")
def home():
    jobs = JobService(get_database()).search({"page": 1, "per_page": 6})
    companies = {
        str(company["_id"]): company for company in get_database()["companies"].find(
            {"_id": {"$in": [job["company_id"] for job in jobs["items"]]}}
        )
    }
    return render_template("home.html", jobs=jobs["items"], companies=companies)


@web.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            user = AuthService(get_database()).register(request.form)
        except HireHubError as error:
            return render_template(
                "auth/register.html", error=str(error), form_data=request.form
            ), error.status_code
        session.clear()
        session["user_id"] = str(user["_id"])
        session.permanent = True
        flash("Welcome to HireHub. Your account is ready.", "success")
        return redirect(url_for("web.dashboard"))
    return render_template("auth/register.html", form_data={})


@web.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            user = AuthService(get_database()).authenticate(
                request.form.get("email"), request.form.get("password")
            )
        except HireHubError as error:
            return render_template(
                "auth/login.html", error=str(error), email=request.form.get("email", "")
            ), error.status_code
        session.clear()
        session["user_id"] = str(user["_id"])
        session.permanent = True
        if user["role"] == "ADMIN":
            return redirect(url_for("web.admin_dashboard"))
        destination = request.args.get("next", "")
        parsed = urlsplit(destination)
        if (
            not destination.startswith("/") or destination.startswith("//")
            or "\\" in destination or parsed.netloc or parsed.scheme
        ):
            destination = url_for("web.dashboard")
        return redirect(destination)
    return render_template("auth/login.html")


@web.post("/logout")
@login_required
def logout():
    user_id = session.get("user_id")
    from app.services.audit_service import AuditService
    AuditService(get_database()).record(user_id, "USER_LOGOUT", "user", user_id)
    session.clear()
    flash("You have signed out.", "success")
    return redirect(url_for("web.home"))


@web.get("/jobs")
def jobs():
    result = JobService(get_database()).search(request.args)
    filter_params = request.args.to_dict()
    filter_params.pop("page", None)
    companies = {
        str(company["_id"]): company
        for company in get_database()["companies"].find(
            {"_id": {"$in": [job["company_id"] for job in result["items"]]}}
        )
    }
    return render_template(
        "jobs/list.html", result=result, companies=companies, filter_params=filter_params
    )


@web.get("/jobs/<job_id>")
def job_detail(job_id):
    job = JobService(get_database()).get(job_id)
    job["company"] = get_database()["companies"].find_one({"_id": job["company_id"]})
    user = current_user_document()
    match = MatchingService().calculate(user, job) if user and user["role"] == "CANDIDATE" else None
    applied = bool(user and user["role"] == "CANDIDATE" and get_database()["applications"].find_one({
        "candidate_id": user["_id"], "job_id": job["_id"],
    }))
    saved = bool(user and user["role"] == "CANDIDATE" and str(job["_id"]) in [
        str(item) for item in user.get("saved_jobs", [])
    ])
    return render_template("jobs/detail.html", job=job, match=match, applied=applied, saved=saved)


@web.post("/jobs/<job_id>/apply")
@role_required("CANDIDATE")
def apply_job(job_id):
    ApplicationService(get_database()).apply(job_id, current_user_document())
    flash("Your application has been submitted.", "success")
    return redirect(url_for("web.job_detail", job_id=job_id))


@web.post("/applications/<application_id>/withdraw")
@role_required("CANDIDATE")
def withdraw_application(application_id):
    ApplicationService(get_database()).withdraw(application_id, current_user_document())
    flash("Your application was withdrawn.", "success")
    return redirect(url_for("web.applications"))


@web.post("/jobs/<job_id>/save")
@role_required("CANDIDATE")
def save_job(job_id):
    job = JobService(get_database()).get(job_id)
    user = current_user_document()
    saved_jobs = [str(item) for item in user.get("saved_jobs", [])]
    if str(job["_id"]) not in saved_jobs:
        saved_jobs.append(str(job["_id"]))
        UserRepository(get_database()).update(user["_id"], {"saved_jobs": saved_jobs})
    flash("Job saved to your profile.", "success")
    return redirect(request.referrer or url_for("web.job_detail", job_id=job_id))


@web.post("/jobs/<job_id>/unsave")
@role_required("CANDIDATE")
def unsave_job(job_id):
    job = JobService(get_database()).get(job_id)
    user = current_user_document()
    saved_jobs = [str(item) for item in user.get("saved_jobs", [])]
    UserRepository(get_database()).update(
        user["_id"], {"saved_jobs": [item for item in saved_jobs if item != str(job["_id"])]}
    )
    flash("Saved job removed.", "success")
    return redirect(request.referrer or url_for("web.job_detail", job_id=job_id))


@web.get("/dashboard")
@login_required
def dashboard():
    user = current_user_document()
    db = get_database()
    if user["role"] == "CANDIDATE":
        applications = list(db["applications"].find(
            {"candidate_id": user["_id"]}, sort=[("applied_at", -1)], limit=10
        ))
        for application in applications:
            application["job"] = db["jobs"].find_one({"_id": application["job_id"]})
        upcoming_interviews = list(db["interviews"].find({
            "candidate_id": user["_id"], "status": "SCHEDULED",
            "date": {"$gte": date.today().isoformat()},
        }).sort([("date", 1), ("time", 1)]).limit(3))
        for interview in upcoming_interviews:
            application = db["applications"].find_one({"_id": interview["application_id"]})
            interview["job"] = db["jobs"].find_one(
                {"_id": application["job_id"]}
            ) if application else None
        recommendations = JobService(db).search({"page": 1, "per_page": 50})["items"]
        applied_job_ids = {
            str(item["job_id"]) for item in db["applications"].find(
                {"candidate_id": user["_id"]}, {"job_id": 1}
            )
        }
        recommendations = [
            {
                "job": {
                    **job,
                    "company": db["companies"].find_one({"_id": job["company_id"]}),
                },
                **MatchingService().calculate(user, job),
            }
            for job in recommendations if str(job["_id"]) not in applied_job_ids
        ]
        recommendations.sort(key=lambda item: item["score"], reverse=True)
        stats = {
            "applications": db["applications"].count_documents({"candidate_id": user["_id"]}),
            "shortlisted": db["applications"].count_documents(
                {"candidate_id": user["_id"], "status": "SHORTLISTED"}
            ),
            "interviews": db["interviews"].count_documents({"candidate_id": user["_id"]}),
            "selections": db["applications"].count_documents(
                {"candidate_id": user["_id"], "status": "SELECTED"}
            ),
            "saved_jobs": len(user.get("saved_jobs", [])),
            "unread_notifications": db["notifications"].count_documents({
                "user_id": user["_id"], "read": False,
            }),
        }
        profile_fields = (
            bool(user.get("name")), bool(user.get("email")), bool(user.get("phone")),
            bool(user.get("location")), bool(user.get("skills")),
            bool(user.get("education")), bool(user.get("experience")),
            bool(user.get("expected_salary")),
            db["resumes"].count_documents({"candidate_id": user["_id"]}) > 0,
        )
        stats["profile_completion"] = round(
            sum(profile_fields) / len(profile_fields) * 100
        )
        return render_template(
            "candidate/dashboard.html", user=user, applications=applications,
            recommendations=recommendations[:3], upcoming_interviews=upcoming_interviews,
            stats=stats,
        )
    if user["role"] == "RECRUITER":
        jobs = list(db["jobs"].find(
            {"recruiter_id": user["_id"]}, sort=[("created_at", -1)], limit=8
        ))
        all_job_ids = [job["_id"] for job in db["jobs"].find(
            {"recruiter_id": user["_id"]}, {"_id": 1}
        )]
        recent_applications = list(db["applications"].find(
            {"job_id": {"$in": all_job_ids}}, sort=[("applied_at", -1)], limit=5
        ))
        for application in recent_applications:
            application["job"] = db["jobs"].find_one({"_id": application["job_id"]})
            application["candidate"] = UserRepository(db).get_by_id(application["candidate_id"])
        total_jobs = db["jobs"].count_documents({"recruiter_id": user["_id"]})
        stats = {
            "active_jobs": db["jobs"].count_documents({
                "recruiter_id": user["_id"], "status": "OPEN",
            }),
            "applications": db["applications"].count_documents({"job_id": {"$in": all_job_ids}}),
            "shortlisted": db["applications"].count_documents({
                "job_id": {"$in": all_job_ids}, "status": "SHORTLISTED",
            }),
            "interviews": db["interviews"].count_documents({
                "recruiter_id": user["_id"], "status": "SCHEDULED",
                "date": {"$gte": date.today().isoformat()},
            }),
            "selections": db["applications"].count_documents({
                "job_id": {"$in": all_job_ids}, "status": "SELECTED",
            }),
        }
        return render_template(
            "recruiter/dashboard.html", user=user, jobs=jobs,
            total_jobs=total_jobs,
            applications=recent_applications, stats=stats,
        )
    return redirect(url_for("web.admin_dashboard"))


@web.route("/profile", methods=["GET", "POST"])
@role_required("CANDIDATE")
def profile():
    db = get_database()
    user = current_user_document()
    if request.method == "POST":
        changes = {
            "name": request.form.get("name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "location": request.form.get("location", "").strip(),
            "skills": AuthService._skills(request.form.get("skills", "")),
            "notice_period": request.form.get("notice_period", "").strip(),
        }
        if not changes["name"] or len(changes["name"]) > 120:
            raise ValidationError("Enter a name no longer than 120 characters.")
        try:
            changes["experience_years"] = float(request.form.get("experience_years") or 0)
            salary = request.form.get("expected_salary", "").strip()
            changes["expected_salary"] = float(salary) if salary else None
            changes["education"] = _parse_profile_entries(
                request.form.get("education", ""), ("degree", "institution", "year"),
                numeric_field="year", integer=True,
            )
            changes["experience"] = _parse_profile_entries(
                request.form.get("experience", ""), ("title", "company", "years"),
                numeric_field="years",
            )
        except ValueError as error:
            raise ValidationError(
                "Check profile values. Experience and salary must be numbers; "
                "education and experience entries must use pipe-separated fields."
            ) from error
        if changes["experience_years"] < 0 or (
            changes["expected_salary"] is not None and changes["expected_salary"] < 0
        ):
            raise ValidationError("Experience and expected salary cannot be negative.")
        UserRepository(db).update(user["_id"], changes)
        flash("Your profile was updated.", "success")
        return redirect(url_for("web.profile"))
    resume = db["resumes"].find_one({"candidate_id": user["_id"]})
    return render_template("candidate/profile.html", user=user, resume=resume)


@web.post("/resume")
@role_required("CANDIDATE")
def upload_resume():
    ResumeService(get_database(), current_app.config["UPLOAD_FOLDER"]).upload(
        request.files.get("resume"), current_user_document()
    )
    flash("Resume uploaded successfully.", "success")
    return redirect(url_for("web.profile"))


@web.post("/resume/<resume_id>/delete")
@role_required("CANDIDATE")
def delete_resume(resume_id):
    ResumeService(
        get_database(), current_app.config["UPLOAD_FOLDER"]
    ).delete(resume_id, current_user_document())
    flash("Resume deleted.", "success")
    return redirect(url_for("web.profile"))


@web.get("/resume/<resume_id>")
@login_required
def download_resume(resume_id):
    try:
        resume = BaseRepository(get_database(), "resumes").get_by_id(resume_id)
    except (TypeError, ValueError):
        resume = None
    user = current_user_document()
    if not resume:
        abort(404)
    if user["role"] == "RECRUITER":
        job_ids = [item["_id"] for item in get_database()["jobs"].find(
            {"recruiter_id": user["_id"]}, {"_id": 1}
        )]
        authorized = get_database()["applications"].find_one({
            "candidate_id": resume["candidate_id"], "job_id": {"$in": job_ids},
        })
        if not authorized:
            raise UnauthorizedError(
                "You can only access resumes for candidates who applied to your jobs."
            )
    elif user["role"] != "ADMIN" and user["_id"] != resume["candidate_id"]:
        raise UnauthorizedError("You cannot access this resume.")
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"], resume["stored_name"], as_attachment=True,
        download_name=secure_filename(resume["filename"]), mimetype=resume["content_type"],
    )


@web.get("/applications")
@role_required("CANDIDATE")
def applications():
    user = current_user_document()
    result = ApplicationRepository(get_database()).list(
        {"candidate_id": user["_id"]}, page=request.args.get("page", 1),
        sort=("applied_at", -1),
    )
    for application in result["items"]:
        application["job"] = get_database()["jobs"].find_one({"_id": application["job_id"]})
    return render_template("candidate/applications.html", result=result)


@web.get("/saved-jobs")
@role_required("CANDIDATE")
def saved_jobs():
    user = current_user_document()
    job_ids = [
        object_id for object_id in
        (BaseRepository.object_id(item) for item in user.get("saved_jobs", []))
        if object_id is not None
    ]
    result = BaseRepository(get_database(), "jobs").list(
        {"_id": {"$in": job_ids}}, page=request.args.get("page", 1),
        sort=("created_at", -1),
    )
    companies = {
        str(company["_id"]): company for company in get_database()["companies"].find(
            {"_id": {"$in": [job["company_id"] for job in result["items"]]}}
        )
    }
    return render_template("candidate/saved_jobs.html", result=result, companies=companies)


@web.get("/interviews")
@login_required
def interviews():
    user = current_user_document()
    query = {"candidate_id": user["_id"]} if user["role"] == "CANDIDATE" else {}
    if user["role"] == "RECRUITER":
        query = {"recruiter_id": user["_id"]}
    if user["role"] == "ADMIN":
        query = {}
    result = BaseRepository(get_database(), "interviews").list(
        query, page=request.args.get("page", 1), sort=("date", 1)
    )
    for interview in result["items"]:
        interview["candidate"] = UserRepository(get_database()).get_by_id(
            interview["candidate_id"]
        )
        application = BaseRepository(get_database(), "applications").get_by_id(
            interview["application_id"]
        )
        interview["job"] = (
            BaseRepository(get_database(), "jobs").get_by_id(application["job_id"])
            if application else None
        )
    return render_template("interviews.html", result=result)


@web.post("/recruiter/interviews/<interview_id>/update")
@role_required("RECRUITER")
def update_interview(interview_id):
    InterviewService(get_database()).update(
        interview_id, request.form, current_user_document()
    )
    flash("Interview updated.", "success")
    return redirect(url_for("web.interviews"))


@web.get("/recruiter/jobs")
@role_required("RECRUITER")
def recruiter_jobs():
    user = current_user_document()
    result = BaseRepository(get_database(), "jobs").list(
        {"recruiter_id": user["_id"]}, page=request.args.get("page", 1), sort=("created_at", -1)
    )
    return render_template("recruiter/jobs.html", result=result)


@web.get("/recruiter/applications")
@role_required("RECRUITER")
def recruiter_applications():
    user = current_user_document()
    job_ids = [job["_id"] for job in get_database()["jobs"].find(
        {"recruiter_id": user["_id"]}, {"_id": 1}
    )]
    query = {"job_id": {"$in": job_ids}}
    status = str(request.args.get("status", "")).upper()
    if status:
        if status not in ApplicationService.TRANSITIONS:
            raise ValidationError("Select a valid application status.")
        query["status"] = status
    result = BaseRepository(get_database(), "applications").list(
        query, page=request.args.get("page", 1),
        sort=("applied_at", -1),
    )
    for application in result["items"]:
        application["job"] = get_database()["jobs"].find_one({"_id": application["job_id"]})
        application["candidate"] = UserRepository(get_database()).get_by_id(
            application["candidate_id"]
        )
        application["resume"] = get_database()["resumes"].find_one(
            {"candidate_id": application["candidate_id"]}
        )
    return render_template("recruiter/applications.html", result=result, status=status)


@web.route("/recruiter/company", methods=["GET", "POST"])
@role_required("RECRUITER")
def recruiter_company():
    service = CompanyService(get_database())
    recruiter = current_user_document()
    if request.method == "POST":
        service.update_for_recruiter(request.form, recruiter)
        flash("Company profile updated. Material changes require verification.", "success")
        return redirect(url_for("web.recruiter_company"))
    return render_template(
        "recruiter/company.html", company=service.get_for_recruiter(recruiter)
    )


@web.route("/recruiter/jobs/new", methods=["GET", "POST"])
@role_required("RECRUITER")
def create_job():
    if request.method == "POST":
        try:
            JobService(get_database()).create(request.form, current_user_document())
        except HireHubError as error:
            return render_template(
                "recruiter/job_form.html", job=None, form_data=request.form,
                error=str(error),
            ), error.status_code
        flash("Job published successfully.", "success")
        return redirect(url_for("web.recruiter_jobs"))
    return render_template("recruiter/job_form.html", job=None, form_data={})


@web.route("/recruiter/jobs/<job_id>/edit", methods=["GET", "POST"])
@role_required("RECRUITER")
def edit_job(job_id):
    service = JobService(get_database())
    job = service.get(job_id)
    if job["recruiter_id"] != current_user_document()["_id"]:
        raise UnauthorizedError("You can only manage your own jobs.")
    if request.method == "POST":
        try:
            service.update(job_id, request.form, current_user_document())
        except HireHubError as error:
            return render_template(
                "recruiter/job_form.html", job=job, form_data=request.form,
                error=str(error),
            ), error.status_code
        flash("Job updated successfully.", "success")
        return redirect(url_for("web.recruiter_jobs"))
    return render_template("recruiter/job_form.html", job=job, form_data={})


@web.post("/recruiter/jobs/<job_id>/close")
@role_required("RECRUITER")
def close_job(job_id):
    JobService(get_database()).update(job_id, {}, current_user_document(), close=True)
    flash("Job closed.", "success")
    return redirect(url_for("web.recruiter_jobs"))


@web.get("/recruiter/jobs/<job_id>/applicants")
@role_required("RECRUITER")
def applicants(job_id):
    job = JobService(get_database()).get(job_id)
    if job["recruiter_id"] != current_user_document()["_id"]:
        raise UnauthorizedError("You can only access applicants for your own jobs.")
    result = BaseRepository(get_database(), "applications").list(
        {"job_id": job["_id"]}, page=request.args.get("page", 1),
        sort=("applied_at", -1),
    )
    for row in result["items"]:
        row["candidate"] = UserRepository(get_database()).get_by_id(row["candidate_id"])
        row["resume"] = get_database()["resumes"].find_one({"candidate_id": row["candidate_id"]})
    return render_template("recruiter/applicants.html", job=job, result=result)


@web.post("/recruiter/applications/<application_id>/status")
@role_required("RECRUITER")
def update_application_status(application_id):
    ApplicationService(get_database()).update_status(
        application_id, request.form.get("status"), current_user_document(),
        request.form.get("recruiter_notes", ""),
    )
    flash("Application updated.", "success")
    return redirect(request.referrer or url_for("web.dashboard"))


@web.route("/recruiter/interviews/new", methods=["GET", "POST"])
@role_required("RECRUITER")
def schedule_interview():
    db = get_database()
    user = current_user_document()
    if request.method == "POST":
        InterviewService(db).create(request.form, user)
        flash("Interview scheduled.", "success")
        return redirect(url_for("web.interviews"))
    jobs = list(db["jobs"].find({"recruiter_id": user["_id"]}, {"_id": 1}))
    apps = list(db["applications"].find({"job_id": {"$in": [job["_id"] for job in jobs]}}))
    for row in apps:
        row["candidate"] = UserRepository(db).get_by_id(row["candidate_id"])
        row["job"] = db["jobs"].find_one({"_id": row["job_id"]})
    return render_template("recruiter/interview_form.html", applications=apps)


@web.get("/notifications")
@login_required
def notifications():
    user = current_user_document()
    result = BaseRepository(get_database(), "notifications").list(
        {"user_id": user["_id"]}, page=request.args.get("page", 1), sort=("created_at", -1)
    )
    return render_template("notifications.html", result=result)


@web.post("/notifications/<notification_id>/read")
@login_required
def mark_notification_read(notification_id):
    repo = BaseRepository(get_database(), "notifications")
    note = repo.get_by_id(notification_id)
    if not note or note["user_id"] != current_user_document()["_id"]:
        raise UnauthorizedError("Notification not found or access denied.")
    repo.update(note["_id"], {"read": True})
    return redirect(url_for("web.notifications"))


@web.get("/admin")
@role_required("ADMIN")
def admin_root():
    return redirect(url_for("web.admin_dashboard"))


@web.get("/admin/dashboard")
@role_required("ADMIN")
def admin_dashboard():
    db = get_database()
    repository = AdminRepository(db)
    stats = AdminService(db).analytics()
    recent_audit_logs = repository.list_audit_logs(page=1, per_page=5)["items"]
    for log in recent_audit_logs:
        log["actor"] = UserRepository(db).get_by_id(log.get("user_id"))
    return render_template(
        "admin/dashboard.html", stats=stats,
        recent_audit_logs=recent_audit_logs,
    )


@web.get("/admin/users")
@web.get("/admin/candidates")
@web.get("/admin/recruiters")
@role_required("ADMIN")
def admin_users():
    role = {
        "/admin/candidates": "CANDIDATE",
        "/admin/recruiters": "RECRUITER",
    }.get(request.path, request.args.get("role", "").upper() or None)
    if role and role not in {"CANDIDATE", "RECRUITER", "ADMIN"}:
        raise ValidationError("Select a valid user role.")
    result = AdminRepository(get_database()).list_users(
        role, page=request.args.get("page", 1)
    )
    return render_template("admin/users.html", result=result, role=role)


@web.post("/admin/users/<user_id>/toggle")
@role_required("ADMIN")
def toggle_user(user_id):
    user = UserRepository(get_database()).get_by_id(user_id)
    if not user or user.get("role") == "ADMIN":
        abort(404)
    AdminService(get_database()).set_user_active(
        user_id, not user.get("is_active", True), current_user_document()
    )
    flash("User status updated.", "success")
    return redirect(request.referrer or url_for("web.admin_users"))


@web.get("/admin/companies")
@role_required("ADMIN")
def admin_companies():
    result = AdminRepository(get_database()).list_companies(
        page=request.args.get("page", 1)
    )
    return render_template("admin/companies.html", result=result)


@web.post("/admin/companies/<company_id>/verify")
@role_required("ADMIN")
def verify_company(company_id):
    company = BaseRepository(get_database(), "companies").get_by_id(company_id)
    if not company:
        abort(404)
    AdminService(get_database()).verify_company(
        company_id, not company.get("verified", False), current_user_document()
    )
    flash("Company verification status updated.", "success")
    return redirect(url_for("web.admin_companies"))


@web.get("/admin/jobs")
@role_required("ADMIN")
def admin_jobs():
    result = AdminRepository(get_database()).list_jobs(page=request.args.get("page", 1))
    for job in result["items"]:
        job["company"] = BaseRepository(get_database(), "companies").get_by_id(
            job["company_id"]
        )
    return render_template("admin/jobs.html", result=result)


@web.post("/admin/jobs/<job_id>/moderate")
@role_required("ADMIN")
def moderate_job(job_id):
    AdminService(get_database()).moderate_job(
        job_id, request.form.get("status"), current_user_document()
    )
    flash("Job moderation status updated.", "success")
    return redirect(url_for("web.admin_jobs"))


@web.get("/admin/applications")
@role_required("ADMIN")
def admin_applications():
    query = {}
    status = request.args.get("status", "").upper()
    if status:
        allowed_statuses = ApplicationService.TRANSITIONS.keys()
        if status not in allowed_statuses:
            raise ValidationError("Select a valid application status.")
        query["status"] = status
    result = AdminRepository(get_database()).list_applications(
        query, page=request.args.get("page", 1)
    )
    for application in result["items"]:
        application["candidate"] = UserRepository(get_database()).get_by_id(
            application["candidate_id"]
        )
        application["job"] = BaseRepository(get_database(), "jobs").get_by_id(
            application["job_id"]
        )
    return render_template("admin/applications.html", result=result, status=status)


@web.get("/admin/analytics")
@role_required("ADMIN")
def admin_analytics():
    return render_template("admin/analytics.html", stats=AdminService(get_database()).analytics())


@web.get("/admin/reports")
@role_required("ADMIN")
def admin_reports():
    report_type = request.args.get("type", "applications")
    headers, rows = ReportService(get_database()).build(report_type, request.args)
    return render_template(
        "admin/reports.html", report_type=report_type,
        headers=headers, rows=rows, filters=request.args,
    )


@web.get("/admin/audit-logs")
@role_required("ADMIN")
def admin_audit_logs():
    result = AdminRepository(get_database()).list_audit_logs(
        page=request.args.get("page", 1)
    )
    for log in result["items"]:
        log["actor"] = UserRepository(get_database()).get_by_id(log.get("user_id"))
    return render_template("admin/audit_logs.html", result=result)


@web.get("/admin/reports/<report_type>.csv")
@role_required("ADMIN")
def download_report(report_type):
    output = io.StringIO()
    writer = csv.writer(output)
    headers, rows = ReportService(get_database()).build(report_type, request.args)
    writer.writerow(headers)
    writer.writerows([_safe_csv_value(value) for value in row] for row in rows)
    return Response(
        output.getvalue(), mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={report_type.lower()}_report.csv"
        },
    )


def _parse_profile_entries(raw, fields, *, numeric_field, integer=False):
    entries = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        values = [value.strip() for value in line.split("|")]
        if len(values) != len(fields) or any(not value for value in values):
            raise ValidationError(
                f"Each {fields[0]} or {fields[1]} entry must have {len(fields)} "
                "pipe-separated values."
            )
        entry = dict(zip(fields, values))
        try:
            entry[numeric_field] = (
                int(entry[numeric_field]) if integer else float(entry[numeric_field])
            )
        except ValueError as error:
            raise ValidationError(
                f"{numeric_field.replace('_', ' ').title()} must be a number."
            ) from error
        if entry[numeric_field] < 0:
            raise ValidationError(f"{numeric_field.replace('_', ' ').title()} cannot be negative.")
        entries.append(entry)
    return entries


def _safe_csv_value(value):
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{value}"
    return value
