from datetime import date, datetime, timezone
from urllib.parse import urlparse

from app.exceptions import (
    ApplicationNotFoundError,
    InterviewNotFoundError,
    InvalidApplicationStatusError,
    UnauthorizedError,
    ValidationError,
)
from app.repositories.base_repository import BaseRepository
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService


class InterviewService:
    TYPES = {"ONLINE", "PHONE", "IN_PERSON"}
    STATUSES = {"SCHEDULED", "COMPLETED", "CANCELLED"}

    def __init__(self, database):
        self.database = database
        self.interviews = BaseRepository(database, "interviews")
        self.applications = BaseRepository(database, "applications")
        self.jobs = BaseRepository(database, "jobs")

    def create(self, data, recruiter):
        application = self.applications.get_by_id(data.get("application_id"))
        if not application:
            raise ApplicationNotFoundError("Application not found.")
        job = self.jobs.get_by_id(application["job_id"])
        if not job or job["recruiter_id"] != recruiter["_id"]:
            raise UnauthorizedError("You can only schedule interviews for your jobs.")
        if application["status"] not in {"SHORTLISTED", "INTERVIEW_SCHEDULED"}:
            raise InvalidApplicationStatusError(
                "Only shortlisted candidates can be scheduled for an interview."
            )
        interview_type = str(data.get("type", "ONLINE")).upper()
        if interview_type not in self.TYPES:
            raise ValidationError("Select a valid interview type.")
        date_value = str(data.get("date", "")).strip()
        time_value = str(data.get("time", "")).strip()
        if not date_value or not time_value:
            raise ValidationError("Interview date and time are required.")
        try:
            scheduled = datetime.fromisoformat(f"{date_value}T{time_value}")
        except ValueError as error:
            raise ValidationError("Interview date and time must be valid.") from error
        if scheduled.date() < date.today():
            raise ValidationError("Interview date cannot be in the past.")
        meeting_link = str(data.get("meeting_link", "")).strip()
        if meeting_link:
            parsed_link = urlparse(meeting_link)
            if parsed_link.scheme != "https" or not parsed_link.netloc:
                raise ValidationError("Meeting link must be a valid HTTPS URL.")

        now = datetime.now(timezone.utc)
        interview = {
            "application_id": application["_id"],
            "candidate_id": application["candidate_id"],
            "recruiter_id": recruiter["_id"],
            "date": date_value,
            "time": time_value,
            "type": interview_type,
            "meeting_link": meeting_link,
            "status": "SCHEDULED",
            "feedback": "",
            "created_at": now,
            "updated_at": now,
        }
        interview_id = self.interviews.insert(interview)
        self.applications.update(application["_id"], {
            "status": "INTERVIEW_SCHEDULED",
            "interview_id": interview_id,
            "updated_at": now,
        })
        NotificationService(self.database).create(
            application["candidate_id"],
            f"An interview is scheduled for {date_value} at {time_value}.",
            "INTERVIEW",
        )
        AuditService(self.database).record(
            recruiter["_id"], "INTERVIEW_SCHEDULED", "interview", interview_id
        )
        interview["_id"] = interview_id
        return interview

    def update(self, interview_id, data, recruiter):
        interview = self.interviews.get_by_id(interview_id)
        if not interview:
            raise InterviewNotFoundError("Interview not found.")
        if interview["recruiter_id"] != recruiter["_id"]:
            raise UnauthorizedError("You can only manage your own interviews.")
        changes = {}
        if "status" in data:
            status = str(data["status"]).upper()
            if status not in self.STATUSES:
                raise ValidationError("Select a valid interview status.")
            if interview["status"] != "SCHEDULED" and status != interview["status"]:
                raise ValidationError("Only scheduled interviews can be updated.")
            changes["status"] = status
        for field in ("date", "time"):
            if field in data:
                changes[field] = str(data[field]).strip()
        if "meeting_link" in data:
            link = str(data["meeting_link"]).strip()
            parsed_link = urlparse(link) if link else None
            if link and (parsed_link.scheme != "https" or not parsed_link.netloc):
                raise ValidationError("Meeting link must be a valid HTTPS URL.")
            changes["meeting_link"] = link
        if "feedback" in data:
            changes["feedback"] = str(data["feedback"]).strip()[:2000]
        if not changes:
            raise ValidationError("Provide at least one interview field to update.")
        date_value = changes.get("date", interview["date"])
        time_value = changes.get("time", interview["time"])
        try:
            scheduled = datetime.fromisoformat(f"{date_value}T{time_value}")
        except ValueError as error:
            raise ValidationError("Interview date and time must be valid.") from error
        if scheduled.date() < date.today() and changes.get("status", interview["status"]) == "SCHEDULED":
            raise ValidationError("A scheduled interview cannot be set in the past.")
        changes["updated_at"] = datetime.now(timezone.utc)
        self.interviews.update(interview["_id"], changes)

        if changes.get("status") == "CANCELLED":
            application = self.applications.get_by_id(interview["application_id"])
            if application and application.get("status") == "INTERVIEW_SCHEDULED":
                self.applications.update(application["_id"], {
                    "status": "SHORTLISTED", "updated_at": changes["updated_at"],
                })
            NotificationService(self.database).create(
                interview["candidate_id"], "Your interview was cancelled.", "INTERVIEW"
            )
            action = "INTERVIEW_CANCELLED"
        elif changes.get("status") == "COMPLETED":
            action = "INTERVIEW_COMPLETED"
        else:
            action = "INTERVIEW_UPDATED"
        AuditService(self.database).record(
            recruiter["_id"], action, "interview", interview["_id"]
        )
        return self.interviews.get_by_id(interview["_id"])
