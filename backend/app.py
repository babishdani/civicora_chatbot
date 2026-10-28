from datetime import datetime, date
from collections import defaultdict, deque
from threading import Lock

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import jwt
import traceback

from login_service import login_user
from config import SECRET_KEY, ALGORITHM
from db import execute_query, get_citizen_mobile_for_auth

from chatbot import (
    ask_database,
    get_public_job_fairs,
    get_public_activities,
    explain_result,
    generate_chat_response,
    detect_civicora_service,
    build_service_response,
)
from scope_guard import classify_question, OUT_OF_SCOPE_REPLY


app = FastAPI(title="Citizen Chatbot API")

# --------------------------------------------------
# Conversation history
# --------------------------------------------------

conversation_histories = defaultdict(
    lambda: deque(maxlen=10)
)

conversation_histories_lock = Lock()

ALLOWED_ROLES = {"citizen"}

# Out-of-scope attempts per user/session
OUT_OF_SCOPE_LIMIT = 3
out_of_scope_attempts = {}

SUPPORT_REPLY = (
    "I'm sorry, I couldn't find support for that request "
    "within Civicora's services. Please contact our support "
    "team at +91 8870556215 for further assistance."
)


def get_conversation_context(conversation_key):
    """Retrieve recent messages for this conversation only."""

    with conversation_histories_lock:
        history = list(
            conversation_histories.get(conversation_key, ())
        )

    if not history:
        return ""

    lines = [
        "Recent conversation history (for follow-up context only):"
    ]

    for item in history:
        role = (
            "Citizen"
            if item["role"] == "user"
            else "Civicora"
        )
        lines.append(f"{role}: {item['text']}")

    return "\n".join(lines)


def add_history_to_context(context, conversation_key):
    """Attach recent conversation context to the LLM prompt."""

    history_context = get_conversation_context(
        conversation_key
    )

    if not history_context:
        return context

    return f"""{context}

{history_context}

CONVERSATION RULES:
- Use earlier messages to understand follow-up references.
- Use verified database records for current factual answers.
- Previous assistant messages are conversation context, not
  independently verified database records.
- Never reveal another user's information.
- Follow all existing authentication and privacy restrictions.
- Do not invent missing database information.
"""


def get_chat_session_key(
    authorization,
    request,
    conversation_id,
):
    """
    Isolate conversation history by authenticated user
    and conversation ID.
    """

    if authorization:
        try:
            user = get_current_user(authorization)
            return f"user:{user['user_id']}"

        except HTTPException:
            # Private-data routes still validate authentication.
            pass

    # Do not share anonymous history using IP address alone.
    return f"anonymous:{conversation_id}"


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
        "https://citizen-service-chatbot-z5qb.vercel.app",
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
    conversation_id: str = Field(min_length=1, max_length=100)


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
# Chat implementation
# --------------------------------------------------

def _chat_impl(
    data: ChatRequest,
    request: Request,
    authorization: str | None = None,
):
    question = data.question.strip()
    conversation_id = data.conversation_id.strip()

    if not conversation_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid conversation ID.",
        )

    session_key = get_chat_session_key(
        authorization,
        request,
        conversation_id,
    )
    conversation_key = f"{session_key}:{conversation_id}"

    if not question:
        return {
            "success": False,
            "answer": "Please enter a question.",
            "public": True,
        }

    q = question.lower()
    login_url = "https://www.ottapidaram.com/citizen"

    try:
        # 1. Safety check
        self_harm_phrases = (
            "how can i die",
            "how i can die",
            "how to die",
            "ways to die",
            "want to die",
            "i want to die",
            "kill myself",
            "end my life",
            "suicide",
            "self harm",
            "self-harm",
            "sethupoganum",
            "saagidanum",
            "en uyira mudichukanum",
        )

        if any(phrase in q for phrase in self_harm_phrases):
            return {
                "success": True,
                "answer": (
                    "I'm sorry you're feeling this way. "
                    "Please reach out to someone you trust or "
                    "a qualified support professional for help."
                ),
                "public": True,
            }

        # Citizen personal information requires login
        citizen_keywords = (
            "my profile",
            "my account",
            "my details",
            "citizen",
            "my personal details",
        )

        if any(keyword in q for keyword in citizen_keywords):
            if not authorization:
                return {
                    "success": True,
                    "answer": (
                        "Please log in to your Citizen Portal to access "
                        "your personal information.\n"
                        f"Login here: {login_url}"
                    ),
                    "public": True,
                    "login_required": True,
                    "login_url": login_url,
                }

        # 2. Grievance requests: preserve authentication
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

            if not authorization:
                context = f"""
                You are Civicora, an Ottapidaram citizen-services assistant.

                The user needs to log in to access grievance details.

                Citizen portal:
                {login_url}

                Explain this politely in the user's language.
                Do not claim that grievance records were checked.
                Do not invent contact details.
                """

                answer = generate_chat_response(
                    question,
                    add_history_to_context(
                        context,
                        conversation_key,
                    ),
                )

                return {
                    "success": True,
                    "answer": answer,
                    "public": True,
                    "login_required": True,
                    "login_url": login_url,
                }

            current_user = get_current_user(authorization)

            if current_user["role"] != "citizen":
                raise HTTPException(
                    status_code=403,
                    detail="Grievance access is available to citizens only.",
                )

            mobile_number = get_citizen_mobile_for_auth(
                current_user["user_id"]
            )

            if not mobile_number:
                raise HTTPException(
                    status_code=401,
                    detail="Citizen account not found. Please log in again.",
                )

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

            context = f"""
            You are Civicora, an Ottapidaram citizen-services assistant.

            Use only the authenticated citizen's records below.
            Explain grievance status clearly and naturally.
            Never invent status, dates, or progress.
            If no records are returned, say that no linked records
            were found.

            Verified grievance records:
            {grievance_rows}
            """

            answer = generate_chat_response(
                question,
                add_history_to_context(
                    context,
                    conversation_key,
                ),
            )

            return {
                "success": True,
                "answer": answer,
                "public": False,
                "login_required": False,
            }

        # 3. Events and public programs
        event_keywords = (
            "event",
            "events",
            "upcoming event",
            "upcoming events",
            "program",
            "programs",
        )

        if any(keyword in q for keyword in event_keywords):
            out_of_scope_attempts.pop(session_key, None)

            updates_url = (
                "https://ottapidaram-website.vercel.app/updates"
            )

            return {
                "success": True,
                "answer": (
                    "You can check the latest events and programs "
                    "through the Ottapidaram Citizen Services website:\n"
                    f"{updates_url}"
                ),
                "public": True,
                "redirect_url": updates_url,
            }

        # 4. Constituency updates and development information
        updates_keywords = (
            "constituency event",
            "constituency events",
            "constituency update",
            "constituency updates",
            "development work",
            "development works",
            "events", "event", "constituency", "updates", "update",
            "public event",
            "public events",
            "ward-level progress",
            "ward level progress",
            "ward-level development",
            "ward level development",
            "ward progress",
            "ward development",
            "area development",
            "நிகழ்ச்சிகள்",
            "நிகழ்ச்சி",
            "தொகுதி செய்திகள்",
            "வளர்ச்சிப் பணிகள்",
            "வளர்ச்சி பணிகள்",
            "பொது நிகழ்ச்சிகள்",
            "வார்டு வளர்ச்சி",
            "சமீபத்திய நிகழ்வுகள்",
            "nigazhchigal",
            "thoguthi seithigal",
            "valarchi panigal",
            "ward valarchi",
        )

        if any(keyword in q for keyword in updates_keywords):
            out_of_scope_attempts.pop(session_key, None)

            updates_url = (
                "https://ottapidaram-website.vercel.app/updates"
            )

            return {
                "success": True,
                "answer": (
                    "For constituency events, development work, public "
                    "events, and ward-level progress, please visit the "
                    "Civicora Updates page:\n"
                    f"{updates_url}"
                ),
                "public": True,
                "redirect_url": updates_url,
            }

        # 5. Livelihood, SHG, employment and placements
        import re

        livelihood_keywords = (
            "livelihood",
            "employment",
            "placement",
            "placements",
            "self help group",
            "self-help group",
            "selfhelp group",
            "shg support",
            "livelihood support",
            "livelihood scheme",
            "livelihood schemes",
            "shg",
            "shgs",
            "women self help group",
            "women's self help group",
            "women empowerment",
            "employment support",
            "job placement",
            "job placements",
            "employment opportunities",
            "income generation",
            "small business support",
            "business support",
            "skill development",
            "vocational training",
            "வாழ்வாதாரம்",
            "சுய உதவிக் குழு",
            "சுய உதவி குழு",
            "மகளிர் சுய உதவிக் குழு",
            "வேலைவாய்ப்பு",
            "வேலை வாய்ப்பு",
            "தொழில் பயிற்சி",
            "தொழில் தொடங்க உதவி",
            "பெண்கள் மேம்பாடு",
            "vaazhvathaaram",
            "suy uthavi kuzhu",
            "magalir suy uthavi kuzhu",
            "velaivaippu",
            "thozhil payirchi",
        )

        is_livelihood_question = (
            any(keyword in q for keyword in livelihood_keywords)
            or bool(re.search(r"\bshgs?\b", q))
        )

        if is_livelihood_question:
            out_of_scope_attempts.pop(session_key, None)

            livelihood_url = (
                "https://ottapidaram-website.vercel.app/livelihood"
            )

            return {
                "success": True,
                "answer": (
                    "For livelihood support, Self Help Groups (SHGs), "
                    "employment, and placements, please visit the "
                    "Civicora Livelihood page:\n"
                    f"{livelihood_url}"
                ),
                "public": True,
                "redirect_url": livelihood_url,
            }

        # 6. Route other supported Civicora services
        service = detect_civicora_service(question)

        print("SERVICE ROUTING DEBUG")
        print("Question:", question)
        print("Detected service:", service)

        if service:
            out_of_scope_attempts.pop(session_key, None)

            answer = build_service_response(service, question)

            return {
                "success": True,
                "answer": answer,
                "public": True,
            }

        # Blood-related questions: route directly to donor information
        blood_keywords = (
            "blood",
            "donor",
            "donors",
            "blood group",
            "blood type",
            "blood availability",
            "need blood",
            "donate blood",
            "blood donation",
            "blood bank",
            "o positive",
            "o negative",
            "a positive",
            "a negative",
            "b positive",
            "b negative",
            "ab positive",
            "ab negative",
            "o+",
            "o-",
            "a+",
            "a-",
            "b+",
            "b-",
            "ab+",
            "ab-",
            "ரத்தம்",
            "இரத்தம்",
            "ரத்த தானம்",
            "இரத்த தானம்",
            "ரத்த கொடையாளர்",
            "இரத்த கொடையாளர்",
            "ரத்தம் தேவை",
            "இரத்தம் தேவை",
            "ரத்த கொடையாளர்கள்",
            "ரத்தம் கொடுக்க",
            "ratham",
            "iratham",
            "ratha thaanam",
            "ratha donor",
            "ratham venum",
            "ratham thevai",
        )

        if any(keyword in q for keyword in blood_keywords):
            out_of_scope_attempts.pop(session_key, None)

            answer = ask_database(
                question=question,
                role="citizen",
            )

            return {
                "success": True,
                "answer": answer,
                "public": True,
            }

        # Direct routing for Job Fairs - English, Tamil and Tanglish
        job_fair_keywords = (
            "job",
            "jobs",
            "job fair",
            "job fairs",
            "job mela",
            "employment fair",
            "employment fairs",
            "upcoming job",
            "job opportunities",
            "job fair details",
            "job fair date",
            "job fair venue",
            "வேலைவாய்ப்பு முகாம்",
            "வேலை வாய்ப்பு முகாம்",
            "வேலைவாய்ப்பு கண்காட்சி",
            "வேலை தேவை",
            "வேலை கிடைக்குமா",
            "வேலைவாய்ப்பு விவரங்கள்",
            "வேலை வாய்ப்புகள்",
            "வேலைவாய்ப்பு முகாம் எப்போது",
            "வேலைக்கு ஆட்கள் தேர்வு",
            "velaivaippu mugam",
            "velai vaaippu mugam",
            "velai thevai",
            "velai kidaikkuma",
            "velai vaaippugal",
            "job fair eppo",
            "job fair irukka",
            "job mela irukka",
            "job details",
        )

        if any(keyword in q for keyword in job_fair_keywords):
            out_of_scope_attempts.pop(session_key, None)

            result = get_public_job_fairs("citizen")

            context = f"""
            You are Civicora, an Ottapidaram citizen-services assistant.

            The user is asking about job fairs.

            Answer in the same language as the user's question.
            Use only facts from the verified records below.
            Never invent dates, venues, employers, registration links,
            eligibility, or procedures.
            If no job fair records are available, say so clearly.
            Never use Markdown tables.
            Display each job fair as a separate numbered item.
            Put available details on separate lines.
            Do not invent missing values.

            Verified job fair records:
            {result}
            """

            answer = generate_chat_response(
                question,
                add_history_to_context(
                    context,
                    conversation_key,
                ),
            )

            return {
                "success": True,
                "answer": answer,
                "public": True,
            }

        # 7. Classify the remaining question
        intent = classify_question(question)
        print("CHAT INTENT:", intent)

        if intent != "out_of_scope":
            out_of_scope_attempts.pop(session_key, None)

        if intent == "out_of_scope":
            context = """
            You are Civicora, the citizen-services assistant
            for Ottapidaram.

            RESPONSE RULES:
            1. Reply naturally and concisely in the user's language.
            2. For greetings like hi or hello, greet the user.
            3. For acknowledgements like ok, okay, thanks, seri,
               sari, சரி, நன்றி, respond naturally and politely.
            4. If the user says only "ok", do not show an error
               or support escalation message.
            5. For unrelated questions, politely explain that
               you help with Ottapidaram citizen services.
            6. Never invent citizen records, job fair details,
               dates, contact details, or service information.
            7. Do not claim that a database was checked unless
               a database query was actually performed.
            8. Keep the response short and helpful.
            """

            answer = generate_chat_response(
                question,
                add_history_to_context(
                    context,
                    conversation_key,
                ),
            )

            return {
                "success": True,
                "answer": answer,
                "public": True,
                "support_escalated": False,
            }

        # 8. Public blood donor information
        if intent == "blood_donors":
            answer = ask_database(
                question=question,
                role="citizen",
            )

            return {
                "success": True,
                "answer": answer,
                "public": True,
            }

        # 9. Public job fairs
        if intent == "job_fairs":
            result = get_public_job_fairs("citizen")

            context = f"""
            You are Civicora, an Ottapidaram citizen-services assistant.

            The user is asking about job fairs.

            Use only facts in the verified records below.
            Never invent dates, venues, registration links,
            employers, eligibility, or procedures.
            Never use Markdown tables.
            Display each job fair as a separate numbered item.
            Put available fields on separate lines.
            Do not invent missing values.

            Verified job fair records:
            {result}
            """

            answer = generate_chat_response(
                question,
                add_history_to_context(
                    context,
                    conversation_key,
                ),
            )

            return {
                "success": True,
                "answer": answer,
                "public": True,
            }

        # 10. Public activities and events
        if intent == "activities":
            result = get_public_activities("citizen")

            context = f"""
            You are Civicora, an Ottapidaram citizen-services assistant.

            The user is asking about public activities and events.

            Use only facts in the verified records below.
            Do not invent dates, venues, links, or procedures.
            Explain participation steps only when verified.

            Verified public activity records:
            {result}
            """

            answer = generate_chat_response(
                question,
                add_history_to_context(
                    context,
                    conversation_key,
                ),
            )

            return {
                "success": True,
                "answer": answer,
                "public": True,
            }

        # 11. Remaining conversational or unsupported questions
        context = """
        You are Civicora, the citizen-services assistant
        for Ottapidaram.

        You can assist with supported citizen services,
        blood donor information, job fairs, public activities,
        grievance guidance, constituency updates, development work,
        livelihood support, SHGs, employment, and placements.

        Reply naturally and concisely in the user's language.
        Do not invent facts, contact details, phone numbers,
        database records, or service procedures.

        For constituency events, development work, public events,
        or ward-level progress, direct users to:
        https://ottapidaram-website.vercel.app/updates

        For livelihood, SHG, self-help groups, employment,
        or placements, direct users to:
        https://ottapidaram-website.vercel.app/livelihood

        If the request is unrelated to citizen services,
        politely explain Civicora's purpose and redirect
        the user to supported citizen services.

        If the request is unclear, ask one short clarification.
        """

        answer = generate_chat_response(
            question,
            add_history_to_context(
                context,
                conversation_key,
            ),
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
        print("CHAT ERROR DETAILS:", repr(error))
        traceback.print_exc()

        raise HTTPException(
            status_code=503,
            detail=(
                "Civicora is temporarily unavailable. "
                "Please try again in a few moments."
            ),
        ) from error


# --------------------------------------------------
# Chat endpoint: save successful conversation turns
# --------------------------------------------------

@app.post("/chat")
def chat(
    data: ChatRequest,
    request: Request,
    authorization: str | None = Header(default=None),
):
    """
    Process the chat and save recent successful turns.
    """

    response = _chat_impl(
        data,
        request,
        authorization,
    )

    if (
        not isinstance(response, dict)
        or response.get("success") is not True
    ):
        return response

    question = data.question.strip()
    conversation_id = data.conversation_id.strip()

    if not question or not conversation_id:
        return response

    session_key = get_chat_session_key(
        authorization,
        request,
        conversation_id,
    )
    conversation_key = f"{session_key}:{conversation_id}"

    answer = (
        response.get("answer")
        or response.get("response")
        or response.get("message")
    )

    if isinstance(answer, str) and answer.strip():
        with conversation_histories_lock:
            history = conversation_histories[conversation_key]

            history.append({
                "role": "user",
                "text": question[:1000],
            })

            history.append({
                "role": "assistant",
                "text": answer[:4000],
            })

    return response