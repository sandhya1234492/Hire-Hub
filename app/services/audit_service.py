from datetime import datetime, timezone


class AuditService:
    def __init__(self, database):
        self.collection = database["audit_logs"]

    def record(self, user_id, action, resource="", resource_id=None, metadata=None):
        self.collection.insert_one({
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "resource_id": resource_id,
            "timestamp": datetime.now(timezone.utc),
            "metadata": metadata or {},
        })
