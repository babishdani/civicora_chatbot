import re
import os
from google import genai
from schema_prompt import SCHEMA
from db import execute_query, get_connection
from sql_validator import validate_sql

MODEL_NAME = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash"
)
MAX_RESULTS = 20
ALLOWED_ROLES = {"admin", "commander", "citizen"}

FORBIDDEN_IDENTIFIERS = {
    "password", "password_hash", "login_password",
    "otp", "otp_hash", "access_token", "refresh_token",
    "refresh_tokens", "token_hash", "secret_key", "secret",
    "citizen_mobile", "citizen_email", "citizen_name",
    "mobile_number", "phone_number", "email", "address",
    "reporter_name", "reporter_contact",
}

def call_gemini(prompt):
    """Send a prompt to Gemini Cloud API."""

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )

    if not response.text:
        raise RuntimeError(
            "Gemini returned an empty response."
        )

    return response.text.strip()

# --------------------------------------------------
# GENERAL HELPERS
# --------------------------------------------------

def get_value(row, key, index=0, default=None):
    """Read a value from dictionary or tuple database rows."""
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[index]
    except (IndexError, TypeError, KeyError):
        return default


def is_sensitive_request(question):
    """Block credential and bulk personal-data disclosure requests."""
    text = question.lower()

    credential_terms = (
        "password", "password hash", "login_password",
        "otp code", "otp codes", "otp hash",
        "refresh token", "access token", "token hash",
        "secret key", "show secrets",
    )

    if any(term in text for term in credential_terms):
        return True

    private_terms = (
        "mobile number", "mobile numbers",
        "phone number", "phone numbers",
        "email address", "email addresses",
        "contact details", "home address",
        "citizen address",
    )

    bulk_terms = (
        "all citizens", "all users", "every citizen",
        "list all", "show all", "all citizen",
        "citizens' ", "citizen's ",
    )

    return (
        any(term in text for term in private_terms)
        and any(term in text for term in bulk_terms)
    )


def format_records(rows, columns=None):
    if not rows:
        return (
            "I'm sorry, but I couldn't find any matching records "
            "in our database. For further assistance, please contact "
            "our support team at 1234123414. We'll be happy to help you."
        )

    lines = []

    for index, row in enumerate(rows[:MAX_RESULTS], start=1):
        if isinstance(row, dict):
            values = [
                f"{key}: {value}"
                for key, value in row.items()
            ]
        elif columns:
            values = [
                f"{column}: {get_value(row, column, i, '')}"
                for i, column in enumerate(columns)
            ]
        else:
            values = [str(value) for value in row]

        lines.append(f"{index}. " + " | ".join(values))

    return "\n".join(lines)


# --------------------------------------------------
# CITIZEN ACCOUNT
# --------------------------------------------------

def get_citizen_mobile(user_id):
    """Get the registered mobile for the authenticated citizen."""
    if user_id is None:
        raise PermissionError("Authenticated user ID is missing.")

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT mobile_number
            FROM users
            WHERE id = %s
              AND role = 'citizen'
              AND is_active = 1
            LIMIT 1
            """,
            (user_id,),
        )

        row = cursor.fetchone()

        if not row or not row[0]:
            raise PermissionError(
                "No active citizen account was found."
            )

        return str(row[0]).strip()

    finally:
        cursor.close()
        connection.close()


def get_citizen_grievances(mobile_number):
    """Return only grievance fields needed by the citizen."""
    if not mobile_number:
        raise PermissionError(
            "Registered citizen account is unavailable."
        )

    query = """
        SELECT
            grievance_code,
            title,
            category_code,
            status_code,
            work_stage_code,
            work_progress,
            created_at
        FROM grievances
        WHERE citizen_mobile = %s
        ORDER BY created_at DESC
        LIMIT 20
    """

    return execute_query(
        query,
        (mobile_number,),
        role="citizen",
    )


# --------------------------------------------------
# GRIEVANCE COUNTS
# --------------------------------------------------

def get_total_grievances():
    return execute_query(
        """
        SELECT COUNT(*) AS total_grievances
        FROM grievances
        """,
        role="admin",
    )


def format_total_grievances(rows):
    if not rows:
        return "Unable to retrieve the grievance count."

    total = get_value(
        rows[0], "total_grievances", 0, 0
    )

    return f"Total grievances: {total}"


def get_grievance_status_counts():
    return execute_query(
        """
        SELECT status_code, COUNT(*) AS total
        FROM grievances
        GROUP BY status_code
        ORDER BY status_code
        """,
        role="admin",
    )


def format_status_counts(rows):
    if not rows:
        return (
            "I'm sorry, but I couldn't find any matching records in our database. "
            "For further assistance, please contact our support team at 1234123414. "
            "We'll be happy to help you."
        )

    status_map = {
        "GST_SUBMITTED": "Submitted",
        "GST_IN_PROGRESS": "In Progress",
        "GST_RESOLVED": "Resolved",
        "GST_REJECTED": "Rejected",
        "GST_CANCELLED": "Cancelled",
        "GST_CITIZEN_CLOSED": "Closed by Citizen",
    }

    lines = ["Grievance Count by Status:"]

    total = 0

    for row in rows:
        status_code = get_value(row, "status_code", 0, "Unknown")
        count = get_value(row, "count", 1, 0)

        status = status_map.get(status_code, status_code)

        lines.append(f"- {status}: {count}")
        total += int(count or 0)

    lines.append(f"\nTotal Grievances: {total}")

    return "\n".join(lines)

def get_village_grievance_counts():
    return execute_query(
        """
        SELECT village_code, COUNT(*) AS total_grievances
        FROM grievances
        WHERE village_code IS NOT NULL
          AND village_code <> ''
        GROUP BY village_code
        ORDER BY total_grievances DESC
        """,
        role="admin",
    )



def format_village_counts(rows):
    if not rows:
        return "No village grievance records were found."

    village_map = {
        "VIL_ADANUR": "Adanur",
        "VIL_KEELNATTUKURICHI": "Keelnattukurichi",
        "VIL_SIVALARPATTI": "Sivalarpatti",
        "VIL_ACKANAICKENPATTI": "Ackanaickenpatti",
        "VIL_MELANAMBIPURAM": "Melanambipuram",
        "VIL_THITTANKULAM": "Thittankulam",
    }

    lines = ["Grievance Counts by Village:"]

    for row in rows:
        village = get_value(row, "village_code", 0, "Unknown")
        count = get_value(row, "total_grievances", 1, 0)

        readable_village = village_map.get(
            str(village), str(village)
        )

        lines.append(f"- {readable_village}: {count}")

    lines.append(
        f"\nVillages with Recorded Grievances: {len(rows)}"
    )

    return "\n".join(lines)



# --------------------------------------------------
# UNRESOLVED AND PENDING GRIEVANCES
# --------------------------------------------------

def get_unresolved_grievances():
    """Submitted and in-progress grievances only."""
    return execute_query(
        """
        SELECT
            grievance_code,
            title,
            category_code,
            status_code,
            work_stage_code,
            created_at
        FROM grievances
        WHERE status_code IN (
            'GST_SUBMITTED',
            'GST_IN_PROGRESS'
        )
        ORDER BY created_at DESC
        LIMIT 100
        """,
        role="admin",
    )


def format_unresolved_grievances(rows):
    if not rows:
        return (
            "I'm sorry, but I couldn't find any matching records in our database. "
            "For further assistance, please contact our support team at 1234123414. "
            "We'll be happy to help you."
        )

    category_map = {
        "CAT_TRAFFIC_ROAD_SAFETY": "Traffic and Road Safety",
        "CAT_WATER_SUPPLY": "Water Supply",
        "CAT_STREET_LIGHT": "Street Light",
        "CAT_ROAD_DAMAGE": "Road Damage",
    }

    status_map = {
        "GST_SUBMITTED": "Submitted",
        "GST_IN_PROGRESS": "In Progress",
        "GST_RESOLVED": "Resolved",
        "GST_REJECTED": "Rejected",
        "GST_CANCELLED": "Cancelled",
        "GST_CITIZEN_CLOSED": "Closed by Citizen",
    }

    stage_map = {
        "WS_UNTRIAGED": "Awaiting Initial Review",
        "WS_LOGGED": "Logged",
        "WS_VERIFICATION": "Verification",
        "WS_MOBILIZATION": "Mobilization",
        "WS_EXECUTION": "Execution",
        "WS_INSPECTION": "Inspection",
        "WS_RESOLUTION": "Resolution",
        "WS_CLOSED": "Closed",
    }

    lines = ["Unresolved Grievances:"]

    for index, row in enumerate(rows, start=1):
        code = get_value(row, "grievance_code", 0, "Unknown")
        title = get_value(row, "title", 1, "Untitled")
        category_code = get_value(row, "category_code", 2, "Unknown")
        status_code = get_value(row, "status_code", 3, "Unknown")
        stage_code = get_value(row, "work_stage_code", 4, "Unknown")

        category = category_map.get(category_code, category_code)
        status = status_map.get(status_code, status_code)
        stage = stage_map.get(stage_code, stage_code)

        lines.append(
            f"\n{index}. Grievance ID: {code}\n"
            f"   Title: {title}\n"
            f"   Category: {category}\n"
            f"   Status: {status}\n"
            f"   Work Stage: {stage}"
        )

    lines.append(f"\nTotal Unresolved Grievances: {len(rows)}")

    return "\n".join(lines)


def get_pending_grievances():
    return execute_query(
        """
        SELECT
            grievance_code,
            title,
            category_code,
            status_code
        FROM grievances
        WHERE status_code = 'GST_SUBMITTED'
        ORDER BY created_at DESC
        LIMIT 20
        """,
        role="admin",
    )


def get_resolved_grievances():
    return execute_query(
        """
        SELECT
            grievance_code,
            title,
            category_code,
            status_code
        FROM grievances
        WHERE status_code = 'GST_RESOLVED'
        ORDER BY created_at DESC
        LIMIT 20
        """,
        role="admin",
    )



def format_pending_grievances(rows):
    if not rows:
        return "No pending grievances were found."

    status_map = {
        "GST_SUBMITTED": "Submitted",
        "GST_IN_PROGRESS": "In Progress",
        "GST_RESOLVED": "Resolved",
        "GST_REJECTED": "Rejected",
        "GST_CANCELLED": "Cancelled",
        "GST_CITIZEN_CLOSED": "Closed by Citizen",
    }

    category_map = {
        "CAT_TRAFFIC_ROAD_SAFETY": "Traffic and Road Safety",
        "CAT_WATER_SUPPLY": "Water Supply",
        "CAT_STREET_LIGHT": "Street Light",
        "CAT_ROAD_DAMAGE": "Road Damage",
    }

    lines = ["Pending Grievances:"]

    for index, row in enumerate(rows, start=1):
        code = get_value(row, "grievance_code", 0, "Unknown")
        title = get_value(row, "title", 1, "Untitled")
        category = get_value(row, "category_code", 2, "Unknown")
        status = get_value(row, "status_code", 3, "Unknown")

        readable_category = category_map.get(
            str(category), str(category)
        )
        readable_status = status_map.get(
            str(status), str(status)
        )

        lines.append(
            f"{index}. Grievance ID: {code}\n"
            f"   Issue: {title}\n"
            f"   Category: {readable_category}\n"
            f"   Status: {readable_status}"
        )

    lines.append(f"\nTotal Pending Grievances: {len(rows)}")

    return "\n\n".join(lines)


# --------------------------------------------------
# PRIORITY QUERIES
# --------------------------------------------------

def get_high_priority_grievances():
    return execute_query(
        """
        SELECT
            grievance_code,
            title,
            category_code,
            status_code,
            priority_label,
            priority_rank,
            work_progress,
            created_at
        FROM grievances
        WHERE LOWER(COALESCE(priority_label, ''))
                  IN ('high', 'critical')
           OR priority_rank = 'P2'
        ORDER BY created_at DESC
        LIMIT 20
        """,
        role="admin",
    )


def get_high_priority_unresolved_grievances():
    """Return only high-priority unresolved grievances."""
    return execute_query(
        """
        SELECT
            grievance_code,
            title,
            category_code,
            status_code,
            priority_label,
            priority_rank,
            work_progress,
            created_at
        FROM grievances
        WHERE status_code IN (
            'GST_SUBMITTED',
            'GST_IN_PROGRESS'
        )
        AND (
            LOWER(COALESCE(priority_label, ''))
                IN ('high', 'critical')
            OR priority_rank = 'P2'
        )
        ORDER BY created_at DESC
        LIMIT 20
        """,
        role="admin",
    )


def get_high_priority_resolved_grievances():
    """Return only high-priority resolved grievances."""
    return execute_query(
        """
        SELECT
            grievance_code,
            title,
            category_code,
            status_code,
            priority_label,
            priority_rank,
            work_progress,
            created_at
        FROM grievances
        WHERE status_code = 'GST_RESOLVED'
          AND (
              LOWER(COALESCE(priority_label, ''))
                  IN ('high', 'critical')
              OR priority_rank = 'P2'
          )
        ORDER BY created_at DESC
        LIMIT 20
        """,
        role="admin",
    )



def format_high_priority_grievances(rows):
    if not rows:
        return "No matching high-priority grievances were found."

    status_map = {
        "GST_SUBMITTED": "Submitted",
        "GST_IN_PROGRESS": "In Progress",
        "GST_RESOLVED": "Resolved",
        "GST_REJECTED": "Rejected",
        "GST_CANCELLED": "Cancelled",
        "GST_CITIZEN_CLOSED": "Closed by Citizen",
    }

    lines = ["High-Priority Grievances:"]

    for index, row in enumerate(rows, start=1):
        code = get_value(row, "grievance_code", 0, "Unknown")
        title = get_value(row, "title", 1, "Untitled")
        status = get_value(row, "status_code", 3, "Unknown")
        label = get_value(row, "priority_label", 4, "Unknown")
        rank = get_value(row, "priority_rank", 5, "Unknown")

        readable_status = status_map.get(
            str(status), str(status)
        )

        lines.append(
            f"{index}. Grievance ID: {code}\n"
            f"   Issue: {title}\n"
            f"   Priority: {label} ({rank})\n"
            f"   Status: {readable_status}"
        )

    lines.append(
        f"\nTotal High-Priority Grievances: {len(rows)}"
    )

    return "\n\n".join(lines)



# --------------------------------------------------
# GRIEVANCE SEARCH
# --------------------------------------------------

def get_grievance_by_code(grievance_code):
    """Fetch grievance details without personal contact fields."""
    return execute_query(
        """
        SELECT
            grievance_code,
            title,
            category_code,
            description,
            status_code,
            work_stage_code,
            priority_label,
            priority_rank,
            work_progress,
            created_at
        FROM grievances
        WHERE grievance_code = %s
        LIMIT 1
        """,
        (grievance_code,),
        role="admin",
    )


def search_street_light_grievances():
    """Find grievances related to street lights."""
    return execute_query(
        """
        SELECT
            grievance_code,
            title,
            category_code,
            status_code,
            priority_label
        FROM grievances
        WHERE LOWER(COALESCE(category_code, ''))
                  LIKE '%street_light%'
           OR LOWER(COALESCE(title, ''))
                  LIKE '%street light%'
           OR LOWER(COALESCE(description, ''))
                  LIKE '%street light%'
        ORDER BY created_at DESC
        LIMIT 20
        """,
        role="admin",
    )


def format_grievance_details(rows):
    if not rows:
        return "No matching grievance was found."

    row = rows[0]

    fields = [
        ("Grievance Code", "grievance_code", 0),
        ("Title", "title", 1),
        ("Category", "category_code", 2),
        ("Description", "description", 3),
        ("Status", "status_code", 4),
        ("Work Stage", "work_stage_code", 5),
        ("Priority", "priority_label", 6),
        ("Priority Rank", "priority_rank", 7),
        ("Work Progress", "work_progress", 8),
        ("Reported On", "created_at", 9),
    ]

    lines = ["Grievance Details:"]

    for label, key, index in fields:
        value = get_value(row, key, index, None)

        if value is not None and str(value).strip():
            lines.append(f"{label}: {value}")

    return "\n".join(lines)



def format_search_results(rows):
    if not rows:
        return (
            "I'm sorry, but I couldn't find any matching records "
            "in our database. For further assistance, please contact "
            "our support team at 1234123414. We'll be happy to help you."
        )

    status_map = {
        "GST_SUBMITTED": "Submitted",
        "GST_IN_PROGRESS": "In Progress",
        "GST_RESOLVED": "Resolved",
        "GST_REJECTED": "Rejected",
        "GST_CANCELLED": "Cancelled",
        "GST_CITIZEN_CLOSED": "Closed by Citizen",
    }

    category_map = {
        "CAT_TRAFFIC_ROAD_SAFETY": "Traffic and Road Safety",
        "CAT_WATER_SUPPLY": "Water Supply",
        "CAT_STREET_LIGHT": "Street Light",
        "CAT_ROAD_DAMAGE": "Road Damage",
    }

    lines = ["Matching Grievances:"]

    for index, row in enumerate(rows, start=1):
        code = get_value(row, "grievance_code", 0, "Unknown")
        title = get_value(row, "title", 1, "Untitled")
        category = get_value(row, "category_code", 2, "Unknown")
        status = get_value(row, "status_code", 3, "Unknown")

        readable_category = category_map.get(
            str(category), str(category)
        )
        readable_status = status_map.get(
            str(status), str(status)
        )

        lines.append(
            f"{index}. Grievance ID: {code}\n"
            f"   Issue: {title}\n"
            f"   Category: {readable_category}\n"
            f"   Status: {readable_status}"
        )

    lines.append(f"\nTotal Matching Grievances: {len(rows)}")

    return "\n\n".join(lines)



# --------------------------------------------------
# KNOWN QUESTION ROUTING
# --------------------------------------------------

def build_direct_query(question, role="citizen"):
    """
    Run predefined queries only for authorized administrative roles.
    Citizen queries must go through the citizen ownership filter.
    """
    text = question.lower().strip()
    role = str(role or "").strip().lower()

    if role not in ALLOWED_ROLES:
        raise PermissionError("Unsupported role.")

    # Citizen requests must use the dedicated ownership-restricted path.
    if role == "citizen":
        return None

    # 1. Exact grievance code
    code_match = re.search(
        r"\bGRV-\d+\b",
        question,
        re.IGNORECASE,
    )

    if code_match and any(
        word in text
        for word in ("show", "find", "details", "status", "grievance")
    ):
        code = code_match.group(0).upper()
        return "grievance_details", get_grievance_by_code(code)

    # 2. High-priority unresolved grievances
    if (
        "priority" in text
        and any(word in text for word in ("high", "critical"))
        and any(
            phrase in text
            for phrase in (
                "unresolved",
                "not resolved",
                "not yet resolved",
                "pending",
            )
        )
    ):
        return (
            "high_priority_unresolved",
            get_high_priority_unresolved_grievances(),
        )

    # 3. Street-light search
    if any(
        phrase in text
        for phrase in (
            "street light",
            "street lights",
            "street_light",
        )
    ):
        return "street_light_search", search_street_light_grievances()

    # 4. Unresolved grievances
    if any(
        phrase in text
        for phrase in (
            "unresolved grievance",
            "unresolved grievances",
            "grievances not resolved",
            "grievances that are not resolved",
            "not yet resolved grievances",
        )
    ):
        return "unresolved", get_unresolved_grievances()

    # 5. Resolved grievances
    if (
        "resolved" in text
        and "priority" not in text
        and "grievance" in text
        and not any(
            phrase in text
            for phrase in (
                "unresolved",
                "not resolved",
                "not yet resolved",
            )
        )
    ):
        return "resolved", get_resolved_grievances()

    # 6. Status counts
    if (
        "grievance" in text
        and "status" in text
        and any(
            word in text
            for word in ("count", "counts", "group", "number")
        )
    ):
        return "status_counts", get_grievance_status_counts()

    # 7. Village-wise counts
    if "village" in text and "grievance" in text:
        return "village_counts", get_village_grievance_counts()

    # 8. Total grievances
    if (
        "grievance" in text
        and any(
            phrase in text
            for phrase in (
                "total",
                "how many",
                "count all",
                "overall count",
            )
        )
    ):
        return "total", get_total_grievances()

    # 9. Pending grievances
    if "pending" in text and "grievance" in text:
        return "pending", get_pending_grievances()

    # 10. High-priority resolved grievances
    if (
        "priority" in text
        and any(word in text for word in ("high", "critical"))
        and "resolved" in text
    ):
        return (
            "high_priority_resolved",
            get_high_priority_resolved_grievances(),
        )

    # 11. High-priority grievances
    if (
        "priority" in text
        and any(word in text for word in ("high", "critical"))
    ):
        return "high_priority", get_high_priority_grievances()

    return None

# --------------------------------------------------
# SQL GENERATION
# --------------------------------------------------

def generate_sql(question, role):
    """Generate one read-only SQL query."""
    role = str(role).strip().lower()

    if role not in ALLOWED_ROLES:
        raise PermissionError("Unsupported role.")

    role_rules = {
        "admin": """
            ADMIN:
            - Query only tables and columns in the supplied schema.
            - Never select personal contact details by default.
            - Never access credentials, passwords, OTPs, tokens or secrets.
            - Never use SELECT *.
        """,
        "commander": """
            COMMANDER:
            - Query only authorized operational tables and columns.
            - Never select personal contact details by default.
            - Never access credentials, passwords, OTPs, tokens or secrets.
            - Never use SELECT *.
        """,
        "citizen": """
            CITIZEN:
            - Query the grievances table only.
            - Never query users or authentication tables.
            - Never select personal contact details.
            - Never use SELECT *.
            - Backend authorization must enforce record ownership.
        """,
    }[role]

    prompt = f"""
{SCHEMA}

You are a MySQL read-only SQL generator.

RULES:
1. Return exactly one SELECT query without Markdown.
2. Use only supplied tables and columns.
3. Never generate INSERT, UPDATE, DELETE, DROP or modifications.
4. Never use SELECT *.
5. Never access credentials, personal contact fields, OTPs or tokens.
6. Add LIMIT {MAX_RESULTS} to detail queries.
7. Never invent columns or status codes.
8. Do not include comments or multiple SQL statements.
9. Do not generate question-mark placeholders.
10. For unresolved grievances, include both GST_SUBMITTED and
    GST_IN_PROGRESS.
11. Do not return citizen phone numbers, emails or addresses.

Known grievance statuses:
GST_SUBMITTED, GST_IN_PROGRESS, GST_RESOLVED,
GST_CITIZEN_CLOSED, GST_REJECTED, GST_CANCELLED.

{role_rules}

User question:
{question}

SQL:
"""

    sql = call_gemini(prompt)

    # Remove optional Markdown code fences.
    sql = re.sub(
        r"\A\s*```(?:sql)?\s*",
        "",
        sql,
        flags=re.IGNORECASE,
    )
    sql = re.sub(r"\s*```\s*\Z", "", sql).strip()

    return sql


# --------------------------------------------------
# READ-ONLY SQL SECURITY
# --------------------------------------------------

def enforce_read_only_sql(sql):
    """Reject unsafe SQL and sensitive field references."""

    if not isinstance(sql, str) or not sql.strip():
        raise PermissionError("Empty SQL query.")

    sql = sql.strip()

    # Allow one optional trailing semicolon.
    if sql.endswith(";"):
        sql = sql[:-1].strip()

    if not sql:
        raise PermissionError("Empty SQL query.")

    # Reject multiple SQL statements.
    if ";" in sql:
        raise PermissionError(
            "Multiple SQL statements are forbidden."
        )

    # Reject SQL comments.
    if re.search(r"--|#|/\*|\*/", sql):
        raise PermissionError(
            "SQL comments are forbidden."
        )

    # Reject question-mark placeholders.
    if "?" in sql:
        raise PermissionError(
            "Question-mark placeholders are forbidden."
        )

    # Only SELECT statements are allowed.
    if not re.match(r"\ASELECT\b", sql, re.IGNORECASE):
        raise PermissionError(
            "Only SELECT queries are allowed."
        )

    # Reject dangerous keywords and functions.
    if re.search(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|"
        r"REPLACE|GRANT|REVOKE|CALL|EXECUTE|INTO|OUTFILE|"
        r"DUMPFILE|LOAD_FILE|SLEEP|BENCHMARK|HANDLER|"
        r"SET|USE|DO|XA|PREPARE|DEALLOCATE)\b",
        sql,
        re.IGNORECASE,
    ):
        raise PermissionError(
            "Unsafe SQL was blocked."
        )

    # Reject sensitive identifiers.
    for identifier in FORBIDDEN_IDENTIFIERS:
        if re.search(
            rf"\b{re.escape(identifier)}\b",
            sql,
            re.IGNORECASE,
        ):
            raise PermissionError(
                "Sensitive field access is forbidden."
            )

    return sql


# --------------------------------------------------
# CITIZEN SQL OWNERSHIP FILTER
# --------------------------------------------------

def restrict_citizen_query(sql, mobile_number):
    """
    Restrict citizen queries to their own grievances.
    Allow only simple SELECT queries on the grievances table.
    """

    if not mobile_number:
        raise PermissionError(
            "Registered citizen account is unavailable."
        )

    if not isinstance(sql, str) or not sql.strip():
        raise PermissionError("Invalid SQL query.")

    sql = sql.strip()

    # Allow one optional trailing semicolon only.
    if sql.endswith(";"):
        sql = sql[:-1].strip()

    # Reject multiple statements and SQL comments.
    if ";" in sql or re.search(r"--|#|/\*|\*/", sql):
        raise PermissionError(
            "Multiple statements and SQL comments are forbidden."
        )

    # Only SELECT queries are allowed.
    if not re.match(r"\ASELECT\b", sql, re.IGNORECASE):
        raise PermissionError("Only SELECT queries are allowed.")

    # Reject query constructs that can bypass simple ownership checks.
    if re.search(
        r"\b(JOIN|UNION|INTERSECT|EXCEPT|EXISTS|"
        r"WITH|PROCEDURE|INTO|FOR\s+UPDATE|LOCK\s+IN\s+SHARE\s+MODE)\b",
        sql,
        re.IGNORECASE,
    ):
        raise PermissionError(
            "Complex citizen queries are not permitted."
        )

    # Reject nested SELECT statements.
    if re.search(r"\bSELECT\b", sql, re.IGNORECASE)[len("SELECT"):]:
        # This branch is intentionally not used for parsing nested SQL.
        pass

    # Require the grievances table as the only FROM target.
    match = re.match(
        r"\ASELECT\s+.+?\s+FROM\s+`?grievances`?(?=\s|$)",
        sql,
        re.IGNORECASE | re.DOTALL,
    )

    if not match:
        raise PermissionError(
            "Citizens can access only their own grievances."
        )

    remainder = sql[match.end():]

    # Only these clauses are allowed after the table name.
    if remainder.strip() and not re.match(
        r"\s*(WHERE\b|ORDER\s+BY\b|GROUP\s+BY\b|HAVING\b|LIMIT\b)",
        remainder,
        re.IGNORECASE,
    ):
        raise PermissionError(
            "Additional tables are not permitted."
        )

    # Reject subqueries anywhere in the query.
    if re.search(r"\(\s*SELECT\b", sql, re.IGNORECASE):
        raise PermissionError(
            "Subqueries are not permitted for citizen queries."
        )

    # Prevent private contact fields from being selected.
    select_list = re.split(
        r"\bFROM\b",
        sql,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    if re.search(
        r"\b(citizen_mobile|citizen_email|citizen_name|"
        r"mobile_number|phone_number|email|address|"
        r"reporter_name|reporter_contact)\b",
        select_list,
        re.IGNORECASE,
    ):
        raise PermissionError(
            "Private contact details cannot be displayed."
        )

    # Split the WHERE condition from optional trailing clauses.
    clause_match = re.search(
        r"\b(ORDER\s+BY|GROUP\s+BY|HAVING|LIMIT)\b",
        remainder,
        re.IGNORECASE,
    )

    if clause_match:
        main_sql = (
            sql[:match.end()]
            + remainder[:clause_match.start()]
        )
        trailing_clause = remainder[clause_match.start():]
    else:
        main_sql = sql
        trailing_clause = ""

    # Enforce ownership outside the user-generated condition.
    where_match = re.search(
        r"\bWHERE\b",
        main_sql,
        re.IGNORECASE,
    )

    if where_match:
        condition = main_sql[where_match.end():].strip()

        if not condition:
            raise PermissionError("Invalid WHERE condition.")

        safe_sql = (
            main_sql[:where_match.start()]
            + "WHERE ("
            + condition
            + ") AND citizen_mobile = %s"
        )
    else:
        safe_sql = (
            main_sql.rstrip()
            + " WHERE citizen_mobile = %s"
        )

    safe_sql = (
        safe_sql + " " + trailing_clause.strip()
    ).strip()

    return safe_sql, (mobile_number,)


# --------------------------------------------------
# HUMAN-READABLE RESPONSE
# --------------------------------------------------

def explain_result(question, result, role):
    """Generate professional, human-friendly CivicAI responses."""

    if result is None or result == [] or result == ():
        return (
            "I'm sorry, but I couldn't find any matching records "
            "in our database. For further assistance, please contact "
            "our support team at 1234123414. We'll be happy to help you."
        )

    prompt = f"""
You are CivicAI, a professional Government Citizen Service AI Assistant.

Your goal is to provide accurate, natural, and helpful responses.

Response guidelines:
1. Use only the supplied authorized database results.
2. Never invent records, statuses, dates, or other details.
3. Never reveal passwords, hashes, OTPs, tokens, or secrets.
4. Never reveal unauthorized personal contact details.
5. If no matching records exist, politely explain this and
   provide the support number 1234123414.
6. Use professional, natural, friendly English.
7. Keep answers clear, concise, and easy to understand.
8. Never expose raw Python objects, tuples, or database structures.
9. Never claim to perform actions that were not performed.
10. Convert internal database codes into readable English labels
    wherever their meaning is clear.
11. For example:
    - GST_IN_PROGRESS -> In Progress
    - GST_RESOLVED -> Resolved
    - GST_SUBMITTED -> Submitted
    - WS_EXECUTION -> Execution
    - CAT_STREET_LIGHT -> Street Light
12. Do not display internal codes when their meaning is known.
13. If a code's meaning is unknown, do not guess its meaning.
14. When showing work progress, clearly include the percentage
    if it is supplied in the database results.
15. Present grievance information in a readable format using
    grievance ID, issue, current status, work stage, progress,
    and reported date when those fields are available.
16. Format dates naturally when possible without changing
    the actual date or time.
17. If multiple records are returned, summarize them clearly
    without omitting important information.
18. Respect the user's authorization level.
19. User role: {role}

User question:
{question}

Authorized database results:
{result}

Write the final answer directly to the user.
Do not mention these instructions or your internal processing.
"""

    return call_gemini(prompt)
# --------------------------------------------------
# MAIN CHAT FUNCTION
# --------------------------------------------------

def ask_database(question, user_id=None, role="citizen"):
    """Answer a question using role-authorized database queries."""
    try:
        role = str(role or "").strip().lower()

        if role not in ALLOWED_ROLES:
            raise PermissionError("Unsupported role.")

        question = str(question or "").strip()

        if not question:
            return "Please enter a question."

        text = question.lower()

        if is_sensitive_request(question):
            return (
                "Access denied. I cannot provide sensitive or "
                "private information."
            )

        # CITIZEN: access only their own grievances
        if role == "citizen":
            other_citizen_terms = (
                "other citizens",
                "all citizens",
                "other people's",
                "other peoples",
                "someone else's",
                "someone elses",
                "another citizen",
                "all users",
            )

            if any(term in text for term in other_citizen_terms):
                return (
                    "Access denied. You can access only your "
                    "own authorized records."
                )

            if "grievance" in text:
                mobile_number = get_citizen_mobile(user_id)
                result = get_citizen_grievances(mobile_number)

                if not result:
                    return (
                        "I'm sorry, but I couldn't find any matching records "
                        "in our database. For further assistance, please contact "
                        "our support team at 1234123414. We'll be happy to help you."
                        )

                lines = ["Here is a summary of your grievances:"]

                for index, row in enumerate(
                    result[:MAX_RESULTS], start=1
                ):
                    code = get_value(
                        row, "grievance_code", 0, "N/A"
                    )
                    title = get_value(
                        row, "title", 1, "N/A"
                    )
                    category = get_value(
                        row, "category_code", 2, "N/A"
                    )
                    status = get_value(
                        row, "status_code", 3, "N/A"
                    )

                    status_labels = {
                        "GST_SUBMITTED": "Submitted",
                        "GST_IN_PROGRESS": "In Progress",
                        "GST_RESOLVED": "Resolved",
                    }

                    status = status_labels.get(str(status), str(status))

                    stage = get_value(
                        row, "work_stage_code", 4, "N/A"
                    )

                    stage_labels = {
                        "WS_EXECUTION": "Execution",
                    }

                    stage = stage_labels.get(str(stage), str(stage))

                    category_labels = {
                        "CAT_STREET_LIGHT": "Street Light",
                    }

                    category = category_labels.get(
                        str(category), str(category)
                    )

                    progress = get_value(
                        row, "work_progress", 5, "N/A"
                    )
                    created = get_value(
                        row, "created_at", 6, "N/A"
                    )

                    lines.append(
                        f"{index}. Grievance ID: {code}\n"
                        f"   Issue: {title}\n"
                        f"   Category: {category}\n"
                        f"   Status: {status}\n"
                        f"   Work Stage: {stage}\n"
                        f"   Work Progress: {progress}%\n"
                        f"   Reported On: {created}"
                    )

                return "\n\n".join(lines)


        # BLOCK DESTRUCTIVE DATABASE REQUESTS
        destructive_terms = (
            "delete ",
            "drop ",
            "truncate ",
            "update ",
            "insert ",
            "remove ",
            "erase ",
            "modify ",
        )

        if any(term in text for term in destructive_terms):
            return (
                "Access denied. I can only retrieve authorized "
                "information and cannot modify or delete records."
            )

        # ADMIN / COMMANDER: show all grievances
        all_grievance_questions = (
            "show all grievances",
            "show all the grievances",
            "show all grievance",
            "show all the grievance",
            "list all grievances",
            "list all the grievances",
            "list all grievance",
            "list all the grievance",
            "display all grievances",
            "display all the grievances",
            "display all grievance",
            "display all the grievance",
            "all grievances",
            "all the grievances",
            "all grievance",
            "all the grievance",
            "show every grievance",
            "list every grievance",
        )

        if (
            role in ("admin", "commander")
            and any(
                phrase in text
                for phrase in all_grievance_questions
            )
        ):
            result = execute_query(
                """
                SELECT
                    grievance_code,
                    title,
                    category_code,
                    status_code,
                    work_stage_code,
                    work_progress,
                    created_at
                FROM grievances
                ORDER BY created_at DESC
                LIMIT 100
                """,
                role=role,
            )

            if not result:
                return (
                    "I'm sorry, but I couldn't find any matching records "
                    "in our database. For further assistance, please contact "
                    "our support team at 1234123414. We'll be happy to help you."
                    )

            lines = [
                "Here are the grievances listed in the database:"
            ]

            for index, grievance in enumerate(result, start=1):
                code = get_value(
                    grievance, "grievance_code", 0, "N/A"
                )
                title = get_value(
                    grievance, "title", 1, "N/A"
                )
                status = get_value(
                    grievance, "status_code", 3, "N/A"
                )
                stage = get_value(
                    grievance, "work_stage_code", 4, "N/A"
                )
                progress = get_value(
                    grievance, "work_progress", 5, "N/A"
                )
                created = get_value(
                    grievance, "created_at", 6, "N/A"
                )

                status_map = {
                    "GST_SUBMITTED": "Submitted",
                    "GST_IN_PROGRESS": "In Progress",
                    "GST_RESOLVED": "Resolved",
                    "GST_REJECTED": "Rejected",
                    "GST_CANCELLED": "Cancelled",
                    "GST_CITIZEN_CLOSED": "Closed by Citizen",
                    }

                stage_map = {
                    "WS_UNTRIAGED": "Awaiting Initial Review",
                    "WS_LOGGED": "Logged",
                    "WS_VERIFICATION": "Verification",
                    "WS_MOBILIZATION": "Mobilization",
                    "WS_EXECUTION": "Execution",
                    "WS_INSPECTION": "Inspection",
                    "WS_RESOLUTION": "Resolution",
                    "WS_CLOSED": "Closed",
                }

                readable_status = status_map.get(str(status), str(status))
                readable_stage = stage_map.get(str(stage), str(stage))

                lines.append(
                    f"{index}. Grievance ID: {code}\n"
                    f"   Issue: {title}\n"
                    f"   Status: {readable_status}\n"
                    f"   Work Stage: {readable_stage}\n"
                    f"   Work Progress: {progress}%\n"
                    f"   Reported On: {created}"
                )

            return "\n".join(lines)

        # DIRECT DATABASE QUERIES
        direct = build_direct_query(question, role = role)

        if direct is not None:
            query_type, result = direct

            if query_type == "grievance_details":
                return format_grievance_details(result)

            if query_type == "street_light_search":
                return format_search_results(result)

            if query_type == "unresolved":
                return format_unresolved_grievances(result)

            if query_type == "resolved":
                return format_search_results(result)

            if query_type == "high_priority_unresolved":
                return format_high_priority_grievances(result)

            if query_type == "total":
                return format_total_grievances(result)

            if query_type == "status_counts":
                return format_status_counts(result)

            if query_type == "village_counts":
                return format_village_counts(result)

            if query_type == "pending":
                return format_pending_grievances(result)

            if query_type == "high_priority":
                return format_high_priority_grievances(result)

            if query_type == "high_priority_resolved":
                return format_high_priority_grievances(result)

        # GENERAL SQL GENERATION
        sql = generate_sql(question, role)
        sql = enforce_read_only_sql(sql)

        if not validate_sql(sql):
            return "Unsafe query blocked."

        params = None

        if role == "citizen":
            mobile_number = get_citizen_mobile(user_id)

            sql, params = restrict_citizen_query(
                sql,
                mobile_number,
            )

            sql = enforce_read_only_sql(sql)

            if not validate_sql(sql):
                return "Unsafe query blocked."

        result = execute_query(
            sql,
            params=params,
            role=role,
        )

        if not result:
            return (
                "I'm sorry, but I couldn't find any matching records "
                "in our database. For further assistance, please contact "
                "our support team at 1234123414. We'll be happy to help you."
                )

        if isinstance(result, list):
            result = result[:MAX_RESULTS]

        return explain_result(
            question,
            result,
            role,
        )

    except PermissionError as error:
        print("ACCESS BLOCKED:", str(error))
        return "Access denied. You cannot access those records."

    except Exception as error:
        print(
            "CHATBOT ERROR:",
            type(error).__name__,
            str(error),
        )
        return (
            "Something went wrong while processing your question."
        )
