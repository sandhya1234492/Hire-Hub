from datetime import datetime, timezone

from app.exceptions import (
    ApplicationNotFoundError,
    DuplicateApplicationError,
    InvalidApplicationStatusError,
    JobClosedError,
)
from app.repositories.application_repository import ApplicationRepository
from app.repositories.base_repository import BaseRepository
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService


class ApplicationService:
    TRANSITIONS = {
        "APPLIED": {"UNDER_REVIEW", "SHORTLISTED", "REJECTED", "WITHDRAWN"},
        "UNDER_REVIEW": {"SHORTLISTED", "REJECTED", "WITHDRAWN"},
        "SHORTLISTED": {"INTERVIEW_SCHEDULED", "SELECTED", "REJECTED", "WITHDRAWN"},
        "INTERVIEW_SCHEDULED": {"SELECTED", "REJECTED", "WITHDRAWN"},
        "SELECTED": set(), "REJECTED": set(), "WITHDRAWN": set(),
    }

    def __init__(self, database):
        self.database = database
        self.applications = ApplicationRepository(database)

    def apply(self, job_id, candidate):
        jobs = BaseRepository(self.database, "jobs")
        job = jobs.get_by_id(job_id)
        if not job:
            from app.exceptions import JobNotFoundError
            raise JobNotFoundError("Job not found.")
        deadline = job.get("deadline")
        if deadline and deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if job.get("status") != "OPEN" or (
            deadline and deadline.date() < datetime.now(timezone.utc).date()
        ):
            raise JobClosedError("This job is no longer accepting applications.")
        if self.applications.for_candidate_and_job(candidate["_id"], job["_id"]):
            raise DuplicateApplicationError("You have already applied for this job.")
        now = datetime.now(timezone.utc)
        document = {
            "candidate_id": candidate["_id"], "job_id": job["_id"], "status": "APPLIED",
            "applied_at": now, "updated_at": now, "recruiter_notes": "",
        }
        application_id = self.applications.insert(document)
        NotificationService(self.database).create(
            candidate["_id"], f"Your application for {job['title']} was submitted.", "APPLICATION"
        )
        AuditService(self.database).record(
            candidate["_id"], "APPLICATION_SUBMITTED", "application", application_id
        )
        document["_id"] = application_id
        return document

    def update_status(self, application_id, status, recruiter, notes=""):
        application = self.applications.get_by_id(application_id)
        if not application:
            raise ApplicationNotFoundError("Application not found.")
        job = BaseRepository(self.database, "jobs").get_by_id(application["job_id"])
        if not job or job["recruiter_id"] != recruiter["_id"]:
            from app.exceptions import UnauthorizedError
            raise UnauthorizedError("You can only review applications for your own jobs.")
        status = str(status).upper()
        allowed_transitions = self.TRANSITIONS.get(application["status"], set())
        if status not in allowed_transitions - {"WITHDRAWN", "INTERVIEW_SCHEDULED"}:
            raise InvalidApplicationStatusError(
                f"Cannot change application from {application['status']} to {status}."
            )
        now = datetime.now(timezone.utc)
        changes = {"status": status, "updated_at": now}
        if notes:
            changes["recruiter_notes"] = str(notes).strip()[:2000]
        self.applications.update(application["_id"], changes)
        NotificationService(self.database).create(
            application["candidate_id"],
            f"Your application status changed to {status.replace('_', ' ').lower()}.",
            "APPLICATION_STATUS",
        )
        AuditService(self.database).record(
            recruiter["_id"], f"APPLICATION_{status}", "application", application["_id"]
        )
        return self.applications.get_by_id(application["_id"])

    def withdraw(self, application_id, candidate):
        application = self.applications.get_by_id(application_id)
        if not application or application["candidate_id"] != candidate["_id"]:
            raise ApplicationNotFoundError("Application not found.")
        if application["status"] not in {
            "APPLIED", "UNDER_REVIEW", "SHORTLISTED", "INTERVIEW_SCHEDULED"
        }:
            raise InvalidApplicationStatusError(
                f"An application in {application['status']} status cannot be withdrawn."
            )
        now = datetime.now(timezone.utc)
        self.applications.update(application["_id"], {
            "status": "WITHDRAWN", "updated_at": now,
        })
        job = BaseRepository(self.database, "jobs").get_by_id(application["job_id"])
        if job:
            NotificationService(self.database).create(
                job["recruiter_id"], "A candidate withdrew an application.", "APPLICATION_STATUS"
            )
        AuditService(self.database).record(
            candidate["_id"], "APPLICATION_WITHDRAWN", "application", application["_id"]
        )
        return self.applications.get_by_id(application["_id"])

    def list_for_candidate(self, candidate_id, *, page=1, per_page=20):
        return self.applications.list(
            {"candidate_id": candidate_id}, page=page, per_page=per_page,
            sort=("applied_at", -1),
        )
