from app.repositories.base_repository import BaseRepository


class ApplicationRepository(BaseRepository):
    def __init__(self, database):
        super().__init__(database, "applications")

    def for_candidate_and_job(self, candidate_id, job_id):
        return self.collection.find_one(
            {"candidate_id": candidate_id, "job_id": job_id}
        )
