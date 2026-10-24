from datetime import datetime, timezone

from app.exceptions import JobNotFoundError, UserNotFoundError, ValidationError
from app.repositories.admin_repository import AdminRepository
from app.repositories.base_repository import BaseRepository
from app.services.audit_service import AuditService


class AdminService:
    def __init__(self, database):
        self.database = database
        self.repository = AdminRepository(database)

    def set_user_active(self, user_id, active, admin):
        repository = BaseRepository(self.database, "users")
        user = repository.get_by_id(user_id)
        if not user or user.get("role") == "ADMIN":
            raise UserNotFoundError("Manageable user not found.")
        repository.update(user["_id"], {"is_active": bool(active)})
        action = "USER_ACTIVATED" if active else "USER_DEACTIVATED"
        AuditService(self.database).record(admin["_id"], action, "user", user["_id"])
        return repository.get_by_id(user["_id"])

    def verify_company(self, company_id, verified, admin):
        repository = BaseRepository(self.database, "companies")
        company = repository.get_by_id(company_id)
        if not company:
            raise ValidationError("Company not found.")
        repository.update(company["_id"], {
            "verified": bool(verified),
            "verified_at": datetime.now(timezone.utc) if verified else None,
            "verified_by": admin["_id"] if verified else None,
        })
        AuditService(self.database).record(
            admin["_id"], "COMPANY_VERIFIED" if verified else "COMPANY_UNVERIFIED",
            "company", company["_id"],
        )
        return repository.get_by_id(company["_id"])

    def moderate_job(self, job_id, status, admin):
        status = str(status).upper()
        if status not in {"OPEN", "CLOSED"}:
            raise ValidationError("A moderated job must be OPEN or CLOSED.")
        repository = BaseRepository(self.database, "jobs")
        job = repository.get_by_id(job_id)
        if not job:
            raise JobNotFoundError("Job not found.")
        deadline = job.get("deadline")
        if status == "OPEN" and deadline:
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            if deadline.date() < datetime.now(timezone.utc).date():
                raise ValidationError("An expired job cannot be reopened.")
        repository.update(job["_id"], {
            "status": status, "updated_at": datetime.now(timezone.utc),
            "moderated_by": admin["_id"],
        })
        AuditService(self.database).record(
            admin["_id"], "JOB_MODERATED", "job", job["_id"], {"status": status}
        )
        return repository.get_by_id(job["_id"])

    def analytics(self):
        counts = self.repository.dashboard_counts()
        return {
            **counts,
            "application_statuses": self.repository.application_status_counts(),
            "monthly_registrations": self.repository.monthly_registration_counts(),
            "top_skills": self.repository.top_skills(),
        }
