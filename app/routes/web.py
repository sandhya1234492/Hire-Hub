from datetime import datetime, timezone
import csv
import io

from bson import ObjectId
from flask import (
    Blueprint, Response, abort, current_app, flash, redirect, render_template,
    request, send_from_directory, session, url_for,
)
from werkzeug.utils import secure_filename

from app.exceptions import HireHubError, UnauthorizedError, ValidationError
from app.extensions import get_database
from app.repositories.application_repository import ApplicationRepository
from app.repositories.base_repository import BaseRepository
from app.repositories.user_repository import UserRepository
from app.services.application_service import ApplicationService
from app.services.auth_service import AuthService
from app.services.job_service import JobService
from app.services.matching_service import MatchingService
from app.services.notification_service import NotificationService
from app.services.resume_service import ResumeService
from app.utils.auth import current_user_document, login_required, role_required

web = Blueprint("web", __name__)


@web.app_errorhandler(HireHubError)
def handle_domain_error(error):
    flash(str(error), "danger")
    return redirect(request.referrer or url_for("web.home")), error.status_code


@web.get("/")
def home():
    jobs = JobService(get_database()).search({"page": 1, "per_page": 6})
    return render_template("home.html", jobs=jobs["items"])


@web.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        user = AuthService(get_database()).register(request.form)
        session.clear()
        session["user_id"] = str(user["_id"])
        session.permanent = True
        flash("Welcome to HireHub. Your account is ready.", "success")
        return redirect(url_for("web.dashboard"))
    return render_template("auth/register.html")


@web.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = AuthService(get_database()).authenticate(
            request.form.get("email"), request.form.get("password")
        )
        session.clear()
        session["user_id"] = str(user["_id"])
        session.permanent = True
        return redirect(request.args.get("next") or url_for("web.dashboard"))
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
    companies = {
        str(company["_id"]): company
        for company in get_database()["companies"].find(
            {"_id": {"$in": [job["company_id"] for job in result["items"]]}}
        )
    }
    return render_template("jobs/list.html", result=result, companies=companies)


@web.get("/jobs/<job_id>")
def job_detail(job_id):
    job = JobService(get_database()).get(job_id)
    job["company"] = get_database()["companies"].find_one({"_id": job["company_id"]})
    user = current_user_document()
    match = MatchingService().calculate(user, job) if user and user["role"] == "CANDIDATE" else None
    return render_template("jobs/detail.html", job=job, match=match)


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
        notifications = list(db["notifications"].find(
            {"user_id": user["_id"]}, sort=[("created_at", -1)], limit=5
        ))
        recommendations = JobService(db).search({"page": 1, "per_page": 50})["items"]
        recommendations = [
            {"job": job, **MatchingService().calculate(user, job)}
            for job in recommendations
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
        }
        return render_template(
            "candidate/dashboard.html", user=user, applications=applications,
            notifications=notifications, recommendations=recommendations[:5], stats=stats,
        )
    if user["role"] == "RECRUITER":
        jobs = list(db["jobs"].find({"recruiter_id": user["_id"]}, sort=[("created_at", -1)]))
        job_ids = [job["_id"] for job in jobs]
        recent_applications = list(db["applications"].find(
            {"job_id": {"$in": job_ids}}, sort=[("applied_at", -1)], limit=10
        ))
        for application in recent_applications:
            application["job"] = db["jobs"].find_one({"_id": application["job_id"]})
            application["candidate"] = UserRepository(db).get_by_id(application["candidate_id"])
        stats = {
            "jobs": len(jobs), "active_jobs": sum(job["status"] == "OPEN" for job in jobs),
            "applications": db["applications"].count_documents({"job_id": {"$in": job_ids}}),
        }
        return render_template(
            "recruiter/dashboard.html", user=user, jobs=jobs[:8],
            applications=recent_applications, stats=stats,
        )
    stats = {
        "users": db["users"].count_documents({}),
        "candidates": db["users"].count_documents({"role": "CANDIDATE"}),
        "recruiters": db["users"].count_documents({"role": "RECRUITER"}),
        "companies": db["companies"].count_documents({}),
        "jobs": db["jobs"].count_documents({}),
        "applications": db["applications"].count_documents({}),
    }
    return render_template("admin/dashboard.html", user=user, stats=stats)


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
        try:
            changes["experience_years"] = max(0, float(request.form.get("experience_years") or 0))
            salary = request.form.get("expected_salary", "").strip()
            changes["expected_salary"] = float(salary) if salary else None
        except ValueError as error:
            raise ValidationError("Experience and expected salary must be numbers.") from error
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
    if user["role"] not in {"RECRUITER", "ADMIN"} and user["_id"] != resume["candidate_id"]:
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
    jobs = list(get_database()["jobs"].find(
        {"_id": {"$in": job_ids}}, sort=[("created_at", -1)]
    ))
    companies = {
        str(company["_id"]): company for company in get_database()["companies"].find(
            {"_id": {"$in": [job["company_id"] for job in jobs]}}
        )
    }
    return render_template("candidate/saved_jobs.html", jobs=jobs, companies=companies)


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


@web.get("/recruiter/jobs")
@role_required("RECRUITER")
def recruiter_jobs():
    user = current_user_document()
    result = BaseRepository(get_database(), "jobs").list(
        {"recruiter_id": user["_id"]}, page=request.args.get("page", 1), sort=("created_at", -1)
    )
    return render_template("recruiter/jobs.html", result=result)


@web.route("/recruiter/jobs/new", methods=["GET", "POST"])
@role_required("RECRUITER")
def create_job():
    if request.method == "POST":
        JobService(get_database()).create(request.form, current_user_document())
        flash("Job published successfully.", "success")
        return redirect(url_for("web.recruiter_jobs"))
    return render_template("recruiter/job_form.html")


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
    rows = list(get_database()["applications"].find(
        {"job_id": job["_id"]}, sort=[("applied_at", -1)]
    ))
    for row in rows:
        row["candidate"] = UserRepository(get_database()).get_by_id(row["candidate_id"])
        row["resume"] = get_database()["resumes"].find_one({"candidate_id": row["candidate_id"]})
    return render_template("recruiter/applicants.html", job=job, applications=rows)


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
        application = BaseRepository(db, "applications").get_by_id(
            request.form.get("application_id")
        )
        job = BaseRepository(db, "jobs").get_by_id(application["job_id"]) if application else None
        if not application or not job or job["recruiter_id"] != user["_id"]:
            raise UnauthorizedError("Select a valid application from one of your jobs.")
        interview_type = request.form.get("type", "ONLINE").upper()
        if interview_type not in {"ONLINE", "PHONE", "IN_PERSON"}:
            raise ValidationError("Select a valid interview type.")
        interview = {
            "application_id": application["_id"], "candidate_id": application["candidate_id"],
            "recruiter_id": user["_id"], "date": request.form.get("date", ""),
            "time": request.form.get("time", ""), "type": interview_type,
            "meeting_link": request.form.get("meeting_link", "").strip(),
            "status": "SCHEDULED", "feedback": "",
            "created_at": datetime.now(timezone.utc),
        }
        if application["status"] not in {"SHORTLISTED", "INTERVIEW_SCHEDULED"}:
            from app.exceptions import InvalidApplicationStatusError
            raise InvalidApplicationStatusError("Only shortlisted candidates can be scheduled.")
        interview_id = db["interviews"].insert_one(interview).inserted_id
        db["applications"].update_one(
            {"_id": application["_id"]},
            {"$set": {"status": "INTERVIEW_SCHEDULED", "interview_id": interview_id}},
        )
        NotificationService(db).create(
            application["candidate_id"], "A recruiter scheduled an interview with you.", "INTERVIEW"
        )
        flash("Interview scheduled.", "success")
        return redirect(url_for("web.dashboard"))
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


@web.get("/admin/users")
@role_required("ADMIN")
def admin_users():
    result = BaseRepository(get_database(), "users").list(
        {}, page=request.args.get("page", 1), sort=("created_at", -1)
    )
    return render_template("admin/users.html", result=result)


@web.post("/admin/users/<user_id>/toggle")
@role_required("ADMIN")
def toggle_user(user_id):
    repo = UserRepository(get_database())
    user = repo.get_by_id(user_id)
    if not user:
        abort(404)
    repo.update(user["_id"], {"is_active": not user.get("is_active", True)})
    from app.services.audit_service import AuditService
    AuditService(get_database()).record(
        current_user_document()["_id"], "USER_DEACTIVATED" if user.get("is_active", True)
        else "USER_ACTIVATED", "user", user["_id"],
    )
    flash("User status updated.", "success")
    return redirect(url_for("web.admin_users"))


@web.get("/admin/reports/applications.csv")
@role_required("ADMIN")
def applications_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Application ID", "Candidate ID", "Job ID", "Status", "Applied at"])
    for item in get_database()["applications"].find():
        writer.writerow([
            str(item["_id"]), str(item["candidate_id"]), str(item["job_id"]),
            item["status"], item.get("applied_at", ""),
        ])
    return Response(
        output.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=applications.csv"},
    )
