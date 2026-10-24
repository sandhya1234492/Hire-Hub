from datetime import datetime, timezone
from urllib.parse import urlparse

from app.exceptions import UnauthorizedError, UserNotFoundError, ValidationError
from app.repositories.base_repository import BaseRepository
from app.services.audit_service import AuditService


class CompanyService:
    EDITABLE_FIELDS = ("name", "website", "industry", "size", "location", "description")

    def __init__(self, database):
        self.database = database
        self.companies = BaseRepository(database, "companies")

    def get_for_recruiter(self, recruiter):
        company_id = recruiter.get("company_id")
        company = self.companies.get_by_id(company_id) if company_id else None
        if not company:
            raise UserNotFoundError("Company profile not found.")
        return company

    def update_for_recruiter(self, data, recruiter):
        company = self.get_for_recruiter(recruiter)
        changes = {}
        for field in self.EDITABLE_FIELDS:
            if field in data:
                value = str(data[field]).strip()
                if field == "name" and not value:
                    raise ValidationError("Company name is required.")
                changes[field] = value[:500 if field == "description" else 160]
        if "website" in changes and changes["website"]:
            website = urlparse(changes["website"])
            if website.scheme != "https" or not website.netloc:
                raise ValidationError("Company website must be a valid HTTPS URL.")
        if not changes:
            raise ValidationError("Provide at least one company detail to update.")
        now = datetime.now(timezone.utc)
        changes["updated_at"] = now
        if any(field != "description" for field in changes):
            changes.update({"verified": False, "verified_at": None, "verified_by": None})
        self.companies.update(company["_id"], changes)
        AuditService(self.database).record(
            recruiter["_id"], "COMPANY_PROFILE_UPDATED", "company", company["_id"]
        )
        return self.companies.get_by_id(company["_id"])
