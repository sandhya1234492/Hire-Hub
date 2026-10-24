import re
from datetime import datetime, timezone

from app.exceptions import JobNotFoundError, UnauthorizedError, ValidationError
from app.repositories.base_repository import BaseRepository
from app.repositories.job_repository import JobRepository
from app.services.audit_service import AuditService


class JobService:
    def __init__(self, database):
        self.database = database
        self.jobs = JobRepository(database)

    def search(self, params):
        now = datetime.now(timezone.utc)
        query = {
            "status": "OPEN",
            "$and": [{
                "$or": [
                    {"deadline": {"$exists": False}},
                    {"deadline": None},
                    {"deadline": {"$gte": now}},
                ]
            }],
        }
        for key, field in (
            ("location", "location"), ("work_mode", "work_mode"),
            ("employment_type", "employment_type"),
        ):
            value = params.get(key)
            if value:
                query[field] = re.compile(re.escape(value.strip()), re.IGNORECASE)
        if params.get("skill"):
            skill_patterns = [
                re.compile(re.escape(skill.strip()), re.IGNORECASE)
                for skill in str(params["skill"]).split(",") if skill.strip()
            ]
            query["$and"].extend(
                {"skills": {"$regex": pattern.pattern, "$options": "i"}}
                for pattern in skill_patterns
            )
        if params.get("company"):
            company_ids = [
                item["_id"] for item in self.database["companies"].find(
                    {"name": {"$regex": re.escape(params["company"].strip()), "$options": "i"}},
                    {"_id": 1},
                )
            ]
            query["company_id"] = {"$in": company_ids}
        if params.get("keyword"):
            pattern = re.compile(re.escape(params["keyword"].strip()), re.IGNORECASE)
            keyword_match = [
                {"title": pattern}, {"description": pattern}, {"skills": pattern},
                {"location": pattern},
            ]
            company_ids = [
                item["_id"] for item in self.database["companies"].find(
                    {"name": {"$regex": re.escape(params["keyword"].strip()), "$options": "i"}},
                    {"_id": 1},
                )
            ]
            if company_ids:
                keyword_match.append({"company_id": {"$in": company_ids}})
            query["$and"].append({"$or": keyword_match})
        for param, operator in (("min_salary", "$gte"), ("max_salary", "$lte")):
            raw_value = params.get(param)
            if raw_value:
                try:
                    amount = float(raw_value)
                    if amount < 0:
                        raise ValueError
                except ValueError as error:
                    raise ValidationError(f"{param} must be a non-negative number.") from error
                query.setdefault("salary_max" if operator == "$gte" else "salary_min", {})[
                    operator
                ] = amount
        if params.get("experience") not in (None, ""):
            try:
                experience = float(params.get("experience"))
                if experience < 0:
                    raise ValueError
            except ValueError as error:
                raise ValidationError("experience must be a non-negative number.") from error
            query["experience_min"] = {"$lte": experience}
        try:
            page = int(params.get("page", 1))
            per_page = int(params.get("per_page", 12))
        except (TypeError, ValueError) as error:
            raise ValidationError("Page values must be integers.") from error
        if page < 1 or per_page < 1:
            raise ValidationError("Page values must be positive.")
        sort_options = {
            "newest": ("created_at", -1),
            "salary_asc": ("salary_min", 1),
            "salary_desc": ("salary_max", -1),
        }
        sort = str(params.get("sort", "newest")).lower()
        if sort not in sort_options:
            raise ValidationError("Select a valid sort order.")
        return self.jobs.search(query, page=page, per_page=per_page, sort=sort_options[sort])

    def get(self, job_id):
        job = self.jobs.get_by_id(job_id)
        if not job:
            raise JobNotFoundError("Job not found.")
        return job

    def create(self, data, recruiter):
        title = str(data.get("title", "")).strip()
        description = str(data.get("description", "")).strip()
        if not title or not description:
            raise ValidationError("Job title and description are required.")
        skills = AuthSkills.normalise(data.get("skills", []))
        work_mode = str(data.get("work_mode", "ONSITE")).upper()
        employment_type = str(data.get("employment_type", "FULL_TIME")).upper()
        if work_mode not in {"REMOTE", "HYBRID", "ONSITE"}:
            raise ValidationError("Select a valid work mode.")
        if employment_type not in {"FULL_TIME", "PART_TIME", "INTERNSHIP", "CONTRACT"}:
            raise ValidationError("Select a valid employment type.")
        try:
            salary_min = self._number(data.get("salary_min"))
            salary_max = self._number(data.get("salary_max"))
            experience_min = float(data.get("experience_min") or 0)
            experience_max = float(data.get("experience_max") or 0)
        except (TypeError, ValueError) as error:
            raise ValidationError("Salary and experience values must be numbers.") from error
        if experience_min < 0 or experience_max < experience_min:
            raise ValidationError("Experience range is invalid.")
        if salary_min is not None and salary_max is not None and salary_max < salary_min:
            raise ValidationError("Salary range is invalid.")
        company_id = recruiter.get("company_id")
        if not company_id:
            raise ValidationError("Recruiter must be associated with a company.")
        now = datetime.now(timezone.utc)
        document = {
            "title": title[:160],
            "description": description,
            "company_id": company_id,
            "recruiter_id": recruiter["_id"],
            "skills": skills,
            "location": str(data.get("location", "")).strip()[:120],
            "work_mode": work_mode,
            "employment_type": employment_type,
            "experience_min": experience_min,
            "experience_max": experience_max,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "status": "OPEN",
            "posted_date": now,
            "created_at": now,
            "updated_at": now,
        }
        deadline = str(data.get("deadline", "")).strip()
        if deadline:
            try:
                document["deadline"] = datetime.fromisoformat(deadline).replace(
                    tzinfo=timezone.utc
                )
            except ValueError as error:
                raise ValidationError("Deadline must be a valid date.") from error
            if document["deadline"].date() < now.date():
                raise ValidationError("Deadline cannot be in the past.")
        job_id = self.jobs.insert(document)
        AuditService(self.database).record(
            recruiter["_id"], "JOB_CREATED", "job", job_id, {"title": title}
        )
        document["_id"] = job_id
        return document

    def update(self, job_id, data, recruiter, *, close=False):
        job = self.get(job_id)
        if job["recruiter_id"] != recruiter["_id"]:
            raise UnauthorizedError("You can only manage your own jobs.")
        if close:
            changes = {"status": "CLOSED", "updated_at": datetime.now(timezone.utc)}
            action = "JOB_CLOSED"
        else:
            changes = {}
            for field in ("title", "description", "location"):
                if field in data:
                    value = str(data[field]).strip()
                    if field in {"title", "description"} and not value:
                        raise ValidationError(f"Job {field} cannot be empty.")
                    if field == "title":
                        value = value[:160]
                    if field == "location":
                        value = value[:120]
                    changes[field] = value
            if "skills" in data:
                changes["skills"] = AuthSkills.normalise(data["skills"])
            numeric_fields = {
                "salary_min": self._number,
                "salary_max": self._number,
                "experience_min": lambda value: float(value or 0),
                "experience_max": lambda value: float(value or 0),
            }
            for field, parser in numeric_fields.items():
                if field in data:
                    try:
                        changes[field] = parser(data[field])
                    except (TypeError, ValueError) as error:
                        raise ValidationError(f"{field} must be a non-negative number.") from error
                    if changes[field] is not None and changes[field] < 0:
                        raise ValidationError(f"{field} cannot be negative.")
            minimum_experience = changes.get("experience_min", job.get("experience_min", 0))
            maximum_experience = changes.get("experience_max", job.get("experience_max", 0))
            if maximum_experience < minimum_experience:
                raise ValidationError("Experience range is invalid.")
            minimum_salary = changes.get("salary_min", job.get("salary_min"))
            maximum_salary = changes.get("salary_max", job.get("salary_max"))
            if (
                minimum_salary is not None and maximum_salary is not None
                and maximum_salary < minimum_salary
            ):
                raise ValidationError("Salary range is invalid.")
            if "deadline" in data:
                deadline = str(data.get("deadline", "")).strip()
                if not deadline:
                    changes["deadline"] = None
                else:
                    try:
                        parsed_deadline = datetime.fromisoformat(deadline).replace(
                            tzinfo=timezone.utc
                        )
                    except ValueError as error:
                        raise ValidationError("Deadline must be a valid date.") from error
                    if parsed_deadline.date() < datetime.now(timezone.utc).date():
                        raise ValidationError("Deadline cannot be in the past.")
                    changes["deadline"] = parsed_deadline
            for field, choices in (
                ("work_mode", {"REMOTE", "HYBRID", "ONSITE"}),
                ("employment_type", {"FULL_TIME", "PART_TIME", "INTERNSHIP", "CONTRACT"}),
            ):
                if field in data:
                    value = str(data[field]).upper()
                    if value not in choices:
                        raise ValidationError(f"Invalid {field.replace('_', ' ')}.")
                    changes[field] = value
            changes["updated_at"] = datetime.now(timezone.utc)
            action = "JOB_UPDATED"
        self.jobs.update(job["_id"], changes)
        AuditService(self.database).record(recruiter["_id"], action, "job", job["_id"])
        return self.get(job_id)

    @staticmethod
    def _number(value):
        if value in (None, ""):
            return None
        number = float(value)
        if number < 0:
            raise ValueError
        return number


class AuthSkills:
    @staticmethod
    def normalise(value):
        if isinstance(value, str):
            value = value.split(",")
        if not isinstance(value, list):
            raise ValidationError("Skills must be a list or comma-separated text.")
        return list(dict.fromkeys(str(item).strip()[:60] for item in value if str(item).strip()))[:40]
