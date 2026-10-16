
import jwt
from datetime import datetime, timedelta, timezone

from db import execute_query
from config import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)


ALLOWED_ROLES = {"citizen", "commander", "admin"}


def login_user(mobile_number, password=None, role=None):
    """
    Development-only passwordless login.
    Use only with dummy data in local testing.
    """

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

    # Parameterized SQL query
    query = """
        SELECT id, role
        FROM users
        WHERE mobile_number = %s
          AND role = %s
          AND is_active = 1
        LIMIT 1
    """

    try:
        result = execute_query(
            query,
            (mobile_number, role),
            role="admin",
        )

    except Exception as error:
        print("LOGIN DATABASE ERROR:", type(error).__name__)
        print("LOGIN DATABASE DETAILS:", repr(error))
        raise

    # Validate database result
    if not result:
        return {
            "success": False,
            "message": "Invalid credentials",
        }

    user_id = result[0][0]
    user_role = str(result[0][1]).strip().lower()

    if user_role not in ALLOWED_ROLES or user_role != role:
        return {
            "success": False,
            "message": "Invalid credentials",
        }

    # Generate JWT token
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
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
