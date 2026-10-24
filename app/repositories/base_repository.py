from bson import ObjectId
from bson.errors import InvalidId


class BaseRepository:
    def __init__(self, database, collection_name: str):
        self.collection = database[collection_name]

    @staticmethod
    def object_id(value):
        if isinstance(value, ObjectId):
            return value
        try:
            return ObjectId(value)
        except (InvalidId, TypeError):
            return None

    def get_by_id(self, document_id):
        object_id = self.object_id(document_id)
        return self.collection.find_one({"_id": object_id}) if object_id else None

    def insert(self, document: dict):
        return self.collection.insert_one(document).inserted_id

    def update(self, document_id, changes: dict):
        object_id = self.object_id(document_id)
        if not object_id:
            return False
        return self.collection.update_one({"_id": object_id}, {"$set": changes}).matched_count > 0

    def list(self, query=None, *, page=1, per_page=20, sort=None):
        query = query or {}
        page = max(1, int(page))
        per_page = min(100, max(1, int(per_page)))
        cursor = self.collection.find(query)
        if sort:
            cursor = cursor.sort(*sort)
        total = self.collection.count_documents(query)
        items = list(cursor.skip((page - 1) * per_page).limit(per_page))
        return {"items": items, "total": total, "page": page, "per_page": per_page}
