from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository):
    def __init__(self, database):
        super().__init__(database, "users")

    def get_by_email(self, email):
        return self.collection.find_one({"email": email.lower().strip()})
