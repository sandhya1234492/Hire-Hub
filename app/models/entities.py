from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class User:
    name: str
    email: str
    phone: str
    role: str
    password_hash: str
    id: Any = None
    is_active: bool = True
    created_at: datetime = field(default_factory=utcnow)

    @property
    def display_name(self) -> str:
        return self.name.strip()

    @classmethod
    def from_document(cls, document: dict):
        role_class = {"CANDIDATE": Candidate, "RECRUITER": Recruiter, "ADMIN": Admin}.get(
            document.get("role"), cls
        )
        return role_class(
            name=document["name"],
            email=document["email"],
            phone=document.get("phone", ""),
            role=document["role"],
            password_hash=document["password_hash"],
            id=document.get("_id"),
            is_active=document.get("is_active", True),
            created_at=document.get("created_at", utcnow()),
            **(
                {
                    "location": document.get("location", ""),
                    "skills": document.get("skills", []),
                    "experience_years": document.get("experience_years", 0),
                    "expected_salary": document.get("expected_salary"),
                    "notice_period": document.get("notice_period", ""),
                    "saved_jobs": document.get("saved_jobs", []),
                    "education": document.get("education", []),
                    "experience": document.get("experience", []),
                }
                if role_class is Candidate else
                {"company_id": document.get("company_id")}
                if role_class is Recruiter else {}
            ),
        )


@dataclass
class Candidate(User):
    location: str = ""
    skills: list[str] = field(default_factory=list)
    experience_years: float = 0
    expected_salary: float | None = None
    notice_period: str = ""
    saved_jobs: list[str] = field(default_factory=list)
    education: list[dict] = field(default_factory=list)
    experience: list[dict] = field(default_factory=list)


@dataclass
class Recruiter(User):
    company_id: Any = None


@dataclass
class Admin(User):
    pass


@dataclass
class Company:
    name: str
    id: Any = None
    description: str = ""
    location: str = ""
    website: str = ""
    verified: bool = False


@dataclass
class Job:
    title: str
    description: str
    company_id: Any
    recruiter_id: Any
    skills: list[str] = field(default_factory=list)
    location: str = ""
    work_mode: str = "ONSITE"
    employment_type: str = "FULL_TIME"
    experience_min: float = 0
    experience_max: float = 0
    salary_min: float | None = None
    salary_max: float | None = None
    deadline: datetime | None = None
    status: str = "OPEN"


@dataclass
class Application:
    candidate_id: Any
    job_id: Any
    status: str = "APPLIED"
    recruiter_notes: str = ""
    applied_at: datetime = field(default_factory=utcnow)


@dataclass
class Interview:
    application_id: Any
    candidate_id: Any
    recruiter_id: Any
    date: str
    time: str
    interview_type: str = "ONLINE"
    meeting_link: str = ""
    status: str = "SCHEDULED"
    feedback: str = ""


@dataclass
class Resume:
    candidate_id: Any
    filename: str
    stored_name: str
    content_type: str
    size: int


@dataclass
class Notification:
    user_id: Any
    message: str
    category: str
    read: bool = False
    created_at: datetime = field(default_factory=utcnow)
