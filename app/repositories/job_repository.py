from app.repositories.base_repository import BaseRepository


class JobRepository(BaseRepository):
    def __init__(self, database):
        super().__init__(database, "jobs")

    def search(self, query, *, page=1, per_page=12):
        return self.list(query, page=page, per_page=per_page, sort=("created_at", -1))
