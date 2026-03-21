from pymongo import MongoClient
from app.config import MONGO_URI, MONGO_DB_NAME

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client


def get_db():
    return get_client()[MONGO_DB_NAME]


def get_books_collection():
    return get_db()["books"]
