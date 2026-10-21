from datetime import datetime, date

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import jwt

from login_service import login_user
from config import SECRET_KEY, ALGORITHM
from db import execute_query, get_citizen_mobile_for_auth

from chatbot import (
    ask_database,
    get_public_job_fairs,
    get_public_activities,
    explain_result,
    generate_chat_response,
)

app = FastAPI(title="Citizen Chatbot API")

ALLOWED_ROLES = {"citizen"}


# --------------------------------------------------
# Date formatter
# --------------------------------------------------

def format_date(value):
    if value is None or str(value).strip() in ("", "N/A"):
        return "Date not available"

    if isinstance(value, (datetime, date)):
        return f"{value.day} {value.strftime('%B %Y')}"

    text = str(value).strip()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            return f"{parsed.day} {parsed.strftime('%B %Y')}"
        except ValueError:
            continue

    return text


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def row_value(row, key, index):
    """Read values from dictionary, tuple, or list rows."""
    if isinstance(row, dict):
        value = row.get(key, "N/A")
        return value if value is not None else "N/A"

    if isinstance(row, (tuple, list)) and len(row) > index:
        value = row[index]
        return value if value is not None else "N/A"

    return "N/A"


def format_public_records(records, kind):
    """Format public database records."""
    if not records:
        if kind == "job fairs":
            return "No job fairs found in the database."

        return "No public activities found in the database."

    if kind == "job fairs":
        lines = ["Here are the latest job fairs:"]

        for job in records:
            lines.append(
                f"• {row_value(job, 'title', 1)} | "
                f"Date: {row_value(job, 'assumed_date', 2)} | "
                f"Venue: {row_value(job, 'venue', 4)} | "
                f"Status: {row_value(job, 'status_code', 3)}"
            )

    else:
        lines = ["Here are the latest public activities:"]

        for activity in records:
            lines.append(
                f"• {row_value(activity, 'title', 1)} | "
                f"Date: {row_value(activity, 'activity_date', 3)} | "
                f"Location: {row_value(activity, 'location', 4)} | "
                f"Status: {row_value(activity, 'status', 6)}"
            )

    return "\n".join(lines)


# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "https://citizen-service-chatbot.vercel.app",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# --------------------------------------------------
# Request models
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
# Login - Development testing only
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

    except HTTPException:
        raise

    except Exception as error:
        print("LOGIN ERROR TYPE:", type(error).__name__)

        raise HTTPException(
            status_code=500,
            detail="Login service is temporarily unavailable.",
        ) from error

    if not isinstance(result, dict) or not result.get("success"):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials.",
        )

    return result


# --------------------------------------------------
# Verify JWT and current database role
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

    try:
        payload = jwt.decode(
            parts[1],
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
        ) from error

    if not isinstance(rows, list) or not rows:
        raise HTTPException(
            status_code=401,
            detail="User account not found. Please log in again.",
        )

    user_row = rows[0]

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
            detail=(
                "User account is inactive or permissions have changed. "
                "Please log in again."
            ),
        )

    return {
        "user_id": user_id,
        "role": db_role,
    }


# --------------------------------------------------
# Chat API
# --------------------------------------------------


@app.post("/chat")
def chat(
    data: ChatRequest,
    authorization: str | None = Header(
        default=None,
        alias="Authorization",
    ),
):
    question = data.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Please enter a question.",
        )

    q = question.lower()

    # --------------------------------------------------
    # 1. Grievance / Petition / Complaint queries
    # --------------------------------------------------

    grievance_keywords = (
        "grievance", "grievances",
        "complaint", "complaints",
        "petition", "petitions",
        "case status", "my case", "my cases",
        "application status", "my application",
        "my applications", "my issue", "my issues",
        "my problem", "my problems",
        "my request", "my requests",
        "my report", "my reports",
        "grievance status", "complaint status",
        "petition status",
        "track my complaint", "track my grievance",
        "track my petition", "track my application",
        "check my complaint", "check my grievance",
        "check my petition",
        "status of my complaint", "status of my grievance",
        "status of my petition",
        "any update on my complaint",
        "any update on my petition",
        "action taken on my complaint",
        "action taken on my petition",
        "manu", "manukkal", "pugaar", "pugar",
        "en manu", "en pugaar", "en complaint",
        "en petition", "en grievance", "en case",
        "en application", "ennoda manu",
        "ennoda complaint", "ennoda petition",
        "ennoda grievance", "ennoda case",
        "ennoda application",
        "complaint status enna", "petition status enna",
        "manu status", "manu enna aachu",
        "complaint enna aachu", "petition enna aachu",
        "status enna",
    )

    if any(keyword in q for keyword in grievance_keywords):
        login_url = "https://www.ottapidaram.com/citizen"

        # Guest users cannot access grievance details.
        if not authorization:
            context = f"""
            The user is not logged in.
            Grievance details require authentication.
            Citizen login URL: {login_url}
            Support contact: +91 8870556215.

            Explain politely in the same language as the user's question
            that they must log in to check their complaints.
            Include the login URL.
            Do not claim to have checked their complaint records.
            """

            try:
                answer = generate_chat_response(question, context)

            except Exception as error:
                print("GUEST GRIEVANCE AI ERROR:", type(error).__name__)

                answer = (
                    "Civicora is temporarily unable to respond. "
                    "Please try again in a few moments. "
                    f"You can also log in here: {login_url}"
                )

            return {
                "success": True,
                "answer": answer,
                "public": True,
                "login_required": True,
                "login_url": login_url,
            }

        # Validate token and current account.
        current_user = get_current_user(authorization)

        if current_user["role"] != "citizen":
            raise HTTPException(
                status_code=403,
                detail="Grievance access is available to citizens only.",
            )

        try:
            mobile_number = get_citizen_mobile_for_auth(
                current_user["user_id"]
            )
        except Exception as error:
            print(
                "CITIZEN MOBILE LOOKUP ERROR:",
                type(error).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail="Unable to verify your citizen account right now.",
            ) from error

        if not mobile_number:
            raise HTTPException(
                status_code=401,
                detail="Citizen account not found. Please log in again.",
            )

        # Fetch only this citizen's grievance records.
        try:
            grievance_rows = execute_query(
                """
                SELECT
                    grievance_code,
                    title,
                    description,
                    status_code,
                    work_stage_code,
                    work_progress,
                    created_at,
                    updated_at
                FROM grievances
                WHERE citizen_mobile = %s
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (mobile_number,),
                role="citizen",
            )
        except Exception as error:
            print(
                "GRIEVANCE DATABASE ERROR:",
                type(error).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail="Unable to retrieve grievance details right now.",
            ) from error

        if not grievance_rows:
            answer = (
                "I couldn't find any grievance records linked to "
                "your registered mobile number. For assistance, "
                "contact +91 8870556215."
            )
        else:
            answer = explain_result(
                question,
                grievance_rows,
                "citizen",
            )

        return {
            "success": True,
            "answer": answer,
            "public": False,
            "login_required": False,
        }

    # --------------------------------------------------
    # 2. Public query keywords
    # --------------------------------------------------

    blood_donor_terms = (
        "blood donor",
        "blood donors",
        "blood donation",
        "find a donor",
        "find donors",
        "available donor",
        "available donors",
    )

    job_fair_terms = (
        "job fair",
        "job fairs",
        "jobfair",
        "jobfairs",
    )

    activity_terms = (
        "activity",
        "activities",
        "public event",
        "public events",
        "upcoming event",
        "upcoming events",
        "program",
        "programs",
    )

    try:
        # --------------------------------------------------
        # 3. Blood donor questions
        # --------------------------------------------------

        if any(term in q for term in blood_donor_terms):
            answer = ask_database(
                question=question,
                role="citizen",
            )

            return {
                "success": True,
                "answer": answer,
                "public": True,
            }

        # --------------------------------------------------
        # 4. Job fair questions
        # --------------------------------------------------

        if any(term in q for term in job_fair_terms):
            result = get_public_job_fairs("citizen")

            context = (
                str(result)
                if result
                else "No job fair records were found."
            )

            answer = generate_chat_response(
                question,
                context,
            )

            return {
                "success": True,
                "answer": answer,
                "public": True,
            }

        # --------------------------------------------------
        # 5. Public activities and events
        # --------------------------------------------------

        if any(term in q for term in activity_terms):
            result = get_public_activities("citizen")

            context = (
                str(result)
                if result
                else "No public activity records were found."
            )

            answer = generate_chat_response(
                question,
                context,
            )

            return {
                "success": True,
                "answer": answer,
                "public": True,
            }

        # --------------------------------------------------
        # 6. Greetings, thanks, and general questions
        # --------------------------------------------------

        context = """
        You are Civicora, a citizen services assistant.

        You can help with:
        - Public blood donor information
        - Job fairs
        - Public activities and events
        - General questions about available citizen services

        Grievance details require citizen login.
        For support, contact +91 8870556215.

        Reply in the same language as the user's question.
        Understand Tamil, Tanglish, and English.
        Be friendly, concise, and helpful.
        Do not invent public records or claim that an action
        was completed when it was not.
        """

        answer = generate_chat_response(
            question,
            context,
        )

        return {
            "success": True,
            "answer": answer,
            "public": True,
        }

    except HTTPException:
        raise

    except Exception as error:
        print("CHAT ERROR TYPE:", type(error).__name__)

        raise HTTPException(
            status_code=503,
            detail=(
                "Civicora is temporarily unavailable. "
                "Please try again in a few moments."
            ),
        ) from error