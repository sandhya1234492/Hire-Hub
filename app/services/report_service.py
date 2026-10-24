from datetime import datetime, timezone

from app.exceptions import ValidationError


class ReportService:
    REPORTS = {"candidates", "jobs", "applications", "recruitment", "skills"}
    APPLICATION_STATUSES = {
        "APPLIED", "UNDER_REVIEW", "SHORTLISTED", "INTERVIEW_SCHEDULED",
        "SELECTED", "REJECTED", "WITHDRAWN",
    }

    def __init__(self, database):
        self.database = database

    def build(self, report_type, filters=None):
        report_type = str(report_type).lower()
        if report_type not in self.REPORTS:
            raise ValidationError("Select a valid report type.")
        filters = filters or {}
        query = self._application_filters(filters)
        if report_type == "applications":
            return self._applications(query)
        if report_type == "recruitment":
            return self._recruitment(query)
        if report_type == "jobs":
            return self._jobs(filters)
        if report_type == "candidates":
            return self._candidates(filters)
        return self._skills(filters)

    def _application_filters(self, filters):
        query = {}
        status = str(filters.get("status", "")).strip().upper()
        if status:
            if status not in self.APPLICATION_STATUSES:
                raise ValidationError("Select a valid application status.")
            query["status"] = status
        date_filter = {}
        for key, operator, end_of_day in (
            ("date_from", "$gte", False), ("date_to", "$lte", True),
        ):
            raw = str(filters.get(key, "")).strip()
            if raw:
                try:
                    value = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
                except ValueError as error:
                    raise ValidationError(f"{key} must be a valid date.") from error
                if end_of_day:
                    value = value.replace(hour=23, minute=59, second=59, microsecond=999999)
                date_filter[operator] = value
        if date_filter:
            query["applied_at"] = date_filter
        matching_job_ids = None
        job_id = str(filters.get("job_id", "")).strip()
        if job_id:
            from app.repositories.base_repository import BaseRepository
            object_id = BaseRepository.object_id(job_id)
            if object_id is None:
                raise ValidationError("job_id must be a valid id.")
            matching_job_ids = {object_id}

        company = str(filters.get("company", "")).strip()
        location = str(filters.get("location", "")).strip()
        if company or location:
            job_query = {}
            if location:
                job_query["location"] = {"$regex": self._escape(location), "$options": "i"}
            if company:
                company_ids = [
                    item["_id"] for item in self.database["companies"].find(
                        {"name": {"$regex": self._escape(company), "$options": "i"}},
                        {"_id": 1},
                    )
                ]
                job_query["company_id"] = {"$in": company_ids}
            filter_ids = {
                item["_id"] for item in self.database["jobs"].find(job_query, {"_id": 1})
            }
            matching_job_ids = (
                matching_job_ids & filter_ids if matching_job_ids is not None else filter_ids
            )
        if matching_job_ids is not None:
            query["job_id"] = {"$in": list(matching_job_ids)}
        if date_filter.get("$gte") and date_filter.get("$lte"):
            if date_filter["$gte"] > date_filter["$lte"]:
                raise ValidationError("date_from cannot be after date_to.")
        return query

    def _applications(self, query):
        headers = ["Application ID", "Candidate", "Candidate email", "Job", "Company",
                   "Location", "Status", "Applied at"]
        rows = []
        for application in self.database["applications"].find(query).sort("applied_at", -1).limit(10000):
            candidate = self.database["users"].find_one({"_id": application["candidate_id"]}) or {}
            job = self.database["jobs"].find_one({"_id": application["job_id"]}) or {}
            company = self.database["companies"].find_one({"_id": job.get("company_id")}) or {}
            rows.append([
                str(application["_id"]), candidate.get("name", ""), candidate.get("email", ""),
                job.get("title", ""), company.get("name", ""), job.get("location", ""),
                application.get("status", ""), application.get("applied_at", ""),
            ])
        return headers, rows

    def _recruitment(self, query):
        headers = ["Job", "Company", "Location", "Applications", "Shortlisted",
                   "Interviews", "Selections"]
        grouped = self.database["applications"].aggregate([
            {"$match": query},
            {"$group": {
                "_id": "$job_id",
                "applications": {"$sum": 1},
                "shortlisted": {"$sum": {"$cond": [{"$eq": ["$status", "SHORTLISTED"]}, 1, 0]}},
                "interviews": {"$sum": {"$cond": [{"$eq": ["$status", "INTERVIEW_SCHEDULED"]}, 1, 0]}},
                "selections": {"$sum": {"$cond": [{"$eq": ["$status", "SELECTED"]}, 1, 0]}},
            }},
            {"$sort": {"applications": -1}},
            {"$limit": 10000},
        ])
        rows = []
        for item in grouped:
            job = self.database["jobs"].find_one({"_id": item["_id"]}) or {}
            company = self.database["companies"].find_one({"_id": job.get("company_id")}) or {}
            rows.append([
                job.get("title", ""), company.get("name", ""), job.get("location", ""),
                item["applications"], item["shortlisted"], item["interviews"], item["selections"],
            ])
        return headers, rows

    def _jobs(self, filters):
        query = {}
        if filters.get("location"):
            query["location"] = {"$regex": self._escape(filters["location"]), "$options": "i"}
        if filters.get("company"):
            company_ids = [
                item["_id"] for item in self.database["companies"].find(
                    {"name": {"$regex": self._escape(filters["company"]), "$options": "i"}},
                    {"_id": 1},
                )
            ]
            query["company_id"] = {"$in": company_ids}
        headers = ["Job ID", "Title", "Company", "Location", "Status", "Work mode",
                   "Employment type", "Salary min", "Salary max", "Posted date"]
        rows = []
        for job in self.database["jobs"].find(query).sort("created_at", -1).limit(10000):
            company = self.database["companies"].find_one({"_id": job.get("company_id")}) or {}
            rows.append([
                str(job["_id"]), job.get("title", ""), company.get("name", ""),
                job.get("location", ""), job.get("status", ""),
                job.get("work_mode", ""), job.get("employment_type", ""),
                job.get("salary_min", ""), job.get("salary_max", ""),
                job.get("posted_date", ""),
            ])
        return headers, rows

    def _candidates(self, filters):
        query = {"role": "CANDIDATE"}
        if filters.get("location"):
            query["location"] = {"$regex": self._escape(filters["location"]), "$options": "i"}
        headers = ["Candidate ID", "Name", "Email", "Location", "Skills",
                   "Experience years", "Expected salary", "Notice period", "Joined"]
        rows = [
            [
                str(user["_id"]), user.get("name", ""), user.get("email", ""),
                user.get("location", ""), ", ".join(user.get("skills", [])),
                user.get("experience_years", 0), user.get("expected_salary", ""),
                user.get("notice_period", ""), user.get("created_at", ""),
            ]
            for user in self.database["users"].find(query).sort("created_at", -1).limit(10000)
        ]
        return headers, rows

    def _skills(self, filters):
        job_query = {"status": "OPEN"}
        if filters.get("location"):
            job_query["location"] = {"$regex": self._escape(filters["location"]), "$options": "i"}
        pipeline = [
            {"$match": job_query},
            {"$unwind": "$skills"},
            {"$group": {"_id": "$skills", "openings": {"$sum": 1}}},
            {"$sort": {"openings": -1, "_id": 1}},
            {"$limit": 1000},
        ]
        return ["Skill", "Open jobs"], [
            [item["_id"], item["openings"]]
            for item in self.database["jobs"].aggregate(pipeline)
        ]

    @staticmethod
    def _escape(value):
        import re
        return re.escape(str(value).strip())
