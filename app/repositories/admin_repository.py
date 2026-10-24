from app.repositories.base_repository import BaseRepository


class AdminRepository:
    def __init__(self, database):
        self.database = database

    def list_users(self, role=None, *, page=1, per_page=20):
        query = {"role": role} if role else {}
        return BaseRepository(self.database, "users").list(
            query, page=page, per_page=per_page, sort=("created_at", -1)
        )

    def list_companies(self, *, page=1, per_page=20):
        return BaseRepository(self.database, "companies").list(
            {}, page=page, per_page=per_page, sort=("name", 1)
        )

    def list_jobs(self, *, page=1, per_page=20):
        return BaseRepository(self.database, "jobs").list(
            {}, page=page, per_page=per_page, sort=("created_at", -1)
        )

    def list_applications(self, query=None, *, page=1, per_page=20):
        return BaseRepository(self.database, "applications").list(
            query or {}, page=page, per_page=per_page, sort=("applied_at", -1)
        )

    def list_audit_logs(self, *, page=1, per_page=30):
        return BaseRepository(self.database, "audit_logs").list(
            {}, page=page, per_page=per_page, sort=("timestamp", -1)
        )

    def dashboard_counts(self):
        return {
            "users": self.database["users"].count_documents({}),
            "candidates": self.database["users"].count_documents({"role": "CANDIDATE"}),
            "recruiters": self.database["users"].count_documents({"role": "RECRUITER"}),
            "companies": self.database["companies"].count_documents({}),
            "unverified_companies": self.database["companies"].count_documents(
                {"verified": {"$ne": True}}
            ),
            "jobs": self.database["jobs"].count_documents({}),
            "open_jobs": self.database["jobs"].count_documents({"status": "OPEN"}),
            "applications": self.database["applications"].count_documents({}),
            "interviews": self.database["interviews"].count_documents({}),
            "selections": self.database["applications"].count_documents(
                {"status": "SELECTED"}
            ),
        }

    def application_status_counts(self):
        return list(self.database["applications"].aggregate([
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]))

    def monthly_registration_counts(self):
        return list(self.database["users"].aggregate([
            {"$match": {"created_at": {"$exists": True}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m", "date": "$created_at"}},
                "count": {"$sum": 1},
            }},
            {"$sort": {"_id": 1}},
            {"$limit": 12},
        ]))

    def top_skills(self):
        return list(self.database["jobs"].aggregate([
            {"$match": {"status": "OPEN"}},
            {"$unwind": "$skills"},
            {"$group": {"_id": "$skills", "count": {"$sum": 1}}},
            {"$sort": {"count": -1, "_id": 1}},
            {"$limit": 8},
        ]))
