
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import jwt

from login_service import login_user
from chatbot import ask_database
from role_guard import can_access
from config import SECRET_KEY, ALGORITHM
from db import execute_query


app = FastAPI(title="Citizen Chatbot API")

ALLOWED_ROLES = {"citizen", "commander", "admin"}


# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)



# --------------------------------------------------
# Request Models
# --------------------------------------------------
class LoginRequest(BaseModel):
    mobile_number: str = Field(min_length=1, max_length=30)
    role: str = Field(min_length=1, max_length=20)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


# --------------------------------------------------
# Home
# --------------------------------------------------
@app.get("/")
def home():
    return {
        "success": True,
        "message": "Citizen Chatbot API Running",
    }


# --------------------------------------------------
# Login - Development Testing Only
# --------------------------------------------------
@app.post("/login")
def login(data: LoginRequest):
    role = data.role.strip().lower()
    mobile_number = data.mobile_number.strip()

    if role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=400,
            detail="Invalid role.",
        )

    if not mobile_number:
        raise HTTPException(
            status_code=400,
            detail="Mobile number is required.",
        )

    try:
        result = login_user(
            mobile_number=mobile_number,
            role=role,
        )

    except Exception as error:
        print("LOGIN ERROR TYPE:", type(error).__name__)
        print("LOGIN ERROR DETAILS:", str(error))
        raise HTTPException(
            status_code=500,
            detail="Login service is temporarily unavailable.",
        )

    if not isinstance(result, dict) or not result.get("success"):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials.",
        )

    return result


# --------------------------------------------------
# Verify JWT + Current Database Role
# --------------------------------------------------
def get_current_user(authorization: str | None):
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.strip().split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header. Use Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "role"]},
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_user_id = payload.get("sub")
    token_role = payload.get("role")

    try:
        if isinstance(raw_user_id, bool):
            raise ValueError

        user_id = int(raw_user_id)

        if user_id <= 0:
            raise ValueError

    except (TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Invalid user identity in authentication token.",
        )

    if (
        not isinstance(token_role, str)
        or token_role not in ALLOWED_ROLES
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid role in authentication token.",
        )

    # Verify the current user and role against the database.
    try:
        rows = execute_query(
            """
            SELECT id, role, is_active
            FROM users
            WHERE id = %s
            LIMIT 1
            """,
            (user_id,),
            role="admin",
        )

    except Exception as error:
        print("AUTH DATABASE ERROR:", type(error).__name__)
        raise HTTPException(
            status_code=503,
            detail="Authentication service is temporarily unavailable.",
        )

    if not isinstance(rows, list) or not rows:
        raise HTTPException(
            status_code=401,
            detail="User account not found. Please log in again.",
        )

    user_row = rows[0]

    # Supports dictionary rows and tuple rows.
    if isinstance(user_row, dict):
        db_user_id = user_row.get("id")
        db_role = user_row.get("role")
        is_active = user_row.get("is_active")
    else:
        db_user_id, db_role, is_active = user_row

    if (
        int(db_user_id) != user_id
        or db_role not in ALLOWED_ROLES
        or str(is_active).strip().lower() not in ("1", "true")
        or db_role != token_role
    ):
        raise HTTPException(
            status_code=401,
            detail="User account is inactive or permissions have changed. Please log in again.",
        )

    return {
        "user_id": user_id,
        "role": db_role,
    }


# --------------------------------------------------
# Chat
# --------------------------------------------------
@app.post("/chat")
def chat(
    data: ChatRequest,
    authorization: str | None = Header(
        default=None,
        alias="Authorization",
    ),
):
    user = get_current_user(authorization)

    user_id = user["user_id"]
    role = user["role"]
    question = data.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Please enter a question.",
        )

    if not can_access(role, question):
        raise HTTPException(
            status_code=403,
            detail="Access denied. This request is restricted.",
        )

    try:
        answer = ask_database(
            question=question,
            user_id=user_id,
            role=role,
        )

        return {
            "success": True,
            "answer": answer,
        }

    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Access denied. You cannot access those records.",
        )

    except Exception as error:
        print("CHAT ERROR TYPE:", type(error).__name__)
        print("CHAT ERROR DETAILS:", str(error))
        raise HTTPException(
            status_code=500,
            detail="Chat service is temporarily unavailable.",
        )
