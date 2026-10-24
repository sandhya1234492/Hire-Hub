from datetime import datetime, timezone


class NotificationService:
    def __init__(self, database):
        self.collection = database["notifications"]

    def create(self, user_id, message, category):
        self.collection.insert_one({
            "user_id": user_id,
            "message": message,
            "category": category,
            "read": False,
            "created_at": datetime.now(timezone.utc),
        })
