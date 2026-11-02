
import jwt
from datetime import datetime, timedelta, timezone

from mongo_db import users_collection
from config import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

# Citizen role mattum allowed
ALLOWED_ROLES = {"citizen"}


def login_user(mobile_number, password=None, role=None):

    # Validate mobile number
    if not isinstance(mobile_number, str):
        return {
            "success": False,
            "message": "Invalid login request",
        }

    mobile_number = mobile_number.strip()

    # Validate role
    if not isinstance(role, str):
        return {
            "success": False,
            "message": "Invalid login request",
        }

    role = role.strip().lower()

    if role not in ALLOWED_ROLES or not mobile_number:
        return {
            "success": False,
            "message": "Invalid credentials",
        }

    try:
        # MongoDB-la active citizen account check
        user = users_collection.find_one(
            {
                "mobile_number": mobile_number,
                "role": role,
                "is_active": True,
            },
            {
                "_id": 1,
                "role": 1,
            },
        )

    except Exception as error:
        print("LOGIN DATABASE ERROR:", type(error).__name__)
        raise

    # Account illana login reject
    if not user:
        return {
            "success": False,
            "message": "Invalid credentials",
        }

    user_id = str(user["_id"])
    user_role = str(user.get("role", "")).strip().lower()

    if user_role != "citizen":
        return {
            "success": False,
            "message": "Invalid credentials",
        }

    # Generate JWT token
    now = datetime.now(timezone.utc)

    payload = {
        "sub": user_id,
        "role": user_role,
        "iat": now,
        "exp": now + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        ),
    }

    access_token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    return {
        "success": True,
        "user_id": user_id,
        "role": user_role,
        "access_token": access_token,
        "token_type": "bearer",
        "message": "Login successful",
    }
