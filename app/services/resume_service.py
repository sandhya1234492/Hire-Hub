from pathlib import Path
from uuid import uuid4

from werkzeug.utils import secure_filename

from app.exceptions import ResumeUploadError, UnauthorizedError
from app.services.audit_service import AuditService


class ResumeService:
    ALLOWED = {".pdf": "application/pdf", ".doc": "application/msword",
               ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}

    def __init__(self, database, upload_folder):
        self.database = database
        self.upload_folder = Path(upload_folder)

    def upload(self, file, candidate):
        if not file or not file.filename:
            raise ResumeUploadError("Choose a resume file to upload.")
        original = secure_filename(file.filename)
        extension = Path(original).suffix.lower()
        if extension not in self.ALLOWED:
            raise ResumeUploadError("Resume must be PDF, DOC, or DOCX.")
        if file.mimetype not in {"application/octet-stream", self.ALLOWED[extension]}:
            raise ResumeUploadError("File type does not match its extension.")
        stored_name = f"{uuid4().hex}{extension}"
        path = self.upload_folder / stored_name
        file.save(path)
        size = path.stat().st_size
        if size > 5 * 1024 * 1024:
            path.unlink(missing_ok=True)
            raise ResumeUploadError("Resume must be 5 MB or smaller.")
        metadata = {
            "candidate_id": candidate["_id"], "filename": original,
            "stored_name": stored_name, "content_type": self.ALLOWED[extension], "size": size,
        }
        previous = self.database["resumes"].find_one({"candidate_id": candidate["_id"]})
        result = self.database["resumes"].replace_one(
            {"candidate_id": candidate["_id"]}, metadata, upsert=True
        )
        metadata["_id"] = result.upserted_id if result.upserted_id else previous["_id"]
        if previous:
            old_path = self.upload_folder / previous["stored_name"]
            if old_path.is_file():
                old_path.unlink()
        AuditService(self.database).record(
            candidate["_id"], "RESUME_UPLOADED", "resume", metadata["stored_name"]
        )
        return metadata

    def delete(self, resume_id, candidate):
        from app.repositories.base_repository import BaseRepository

        repository = BaseRepository(self.database, "resumes")
        resume = repository.get_by_id(resume_id)
        if not resume or resume["candidate_id"] != candidate["_id"]:
            raise UnauthorizedError("Resume not found or access denied.")
        path = self.upload_folder / resume["stored_name"]
        if path.is_file():
            path.unlink()
        self.database["resumes"].delete_one({"_id": resume["_id"]})
        AuditService(self.database).record(
            candidate["_id"], "RESUME_DELETED", "resume", resume["stored_name"]
        )
        return True
