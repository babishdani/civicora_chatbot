
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DATABASE = os.getenv(
    "MONGODB_DATABASE",
    "civicora",
)

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is not configured")

client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=10000,
)

db = client[MONGODB_DATABASE]


# MongoDB collections
users_collection = db["users"]
otp_collection = db["otp_codes"]
refresh_tokens_collection = db["refresh_tokens"]


def test_connection():
    client.admin.command("ping")

    return {
        "success": True,
        "message": "MongoDB connection successful",
    }
