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
        return "No matching records were found."

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
        return "No grievance status records were found."

    lines = ["Grievances count by status:"]
    total = 0

    for row in rows:
        status = get_value(row, "status_code", 0, "Unknown")
        count = int(get_value(row, "total", 1, 0) or 0)

        lines.append(f"- {status}: {count}")
        total += count

    lines.append(f"\nTotal grievances: {total}")

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

    lines = ["Grievances count by village:"]

    for row in rows:
        village = get_value(row, "village_code", 0, "Unknown")
        count = get_value(row, "total_grievances", 1, 0)
        lines.append(f"- {village}: {count}")

    lines.append(
        f"\nVillages with recorded grievances: {len(rows)}"
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
        return "No unresolved grievances were found."

    lines = ["Unresolved grievances:"]

    for index, row in enumerate(rows, start=1):
        code = get_value(row, "grievance_code", 0, "Unknown")
        title = get_value(row, "title", 1, "Untitled")
        category = get_value(row, "category_code", 2, "Unknown")
        status = get_value(row, "status_code", 3, "Unknown")
        stage = get_value(row, "work_stage_code", 4, "Unknown")

        lines.append(
            f"{index}. {code} - {title} | "
            f"Category: {category} | "
            f"Status: {status} | Stage: {stage}"
        )

    lines.append(f"\nTotal unresolved grievances: {len(rows)}")

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


def format_pending_grievances(rows):
    if not rows:
        return "No pending grievances were found."

    lines = ["Pending grievances:"]

    for row in rows:
        code = get_value(row, "grievance_code", 0, "Unknown")
        title = get_value(row, "title", 1, "Untitled")
        category = get_value(row, "category_code", 2, "Unknown")
        status = get_value(row, "status_code", 3, "Unknown")

        lines.append(
            f"- {code}: {title} | {category} | {status}"
        )

    lines.append(f"\nTotal pending grievances: {len(rows)}")

    return "\n".join(lines)


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

    lines = ["High-priority grievances:"]

    for row in rows:
        code = get_value(row, "grievance_code", 0, "Unknown")
        title = get_value(row, "title", 1, "Untitled")
        status = get_value(row, "status_code", 3, "Unknown")
        label = get_value(row, "priority_label", 4, "Unknown")
        rank = get_value(row, "priority_rank", 5, "Unknown")

        lines.append(
            f"- {code}: {title} | Priority: {label} ({rank}) "
            f"| Status: {status}"
        )

    lines.append(f"\nTotal matching grievances: {len(rows)}")

    return "\n".join(lines)


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
        return "No matching records were found."

    lines = ["Matching grievances:"]

    for row in rows:
        code = get_value(row, "grievance_code", 0, "Unknown")
        title = get_value(row, "title", 1, "Untitled")
        category = get_value(row, "category_code", 2, "Unknown")
        status = get_value(row, "status_code", 3, "Unknown")

        lines.append(
            f"- {code}: {title} | Category: {category} | Status: {status}"
        )

    lines.append(f"\nTotal matching grievances: {len(rows)}")

    return "\n".join(lines)


# --------------------------------------------------
# KNOWN QUESTION ROUTING
# --------------------------------------------------

def build_direct_query(question):
    """
    Run deterministic queries for known questions.
    Return None if general SQL generation is required.
    """
    text = question.lower().strip()

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

    # 2. Combined filter must come before the general unresolved filter
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
    if (
        "street light" in text
        or "street lights" in text
        or "street_light" in text
    ):
        return "street_light_search", search_street_light_grievances()

    # 4. All unresolved grievances
    if (
        "unresolved grievance" in text
        or "unresolved grievances" in text
        or "grievances not resolved" in text
        or "grievances that are not resolved" in text
        or "not yet resolved grievances" in text
    ):
        return "unresolved", get_unresolved_grievances()

    # 5. Status counts
    if (
        "grievance" in text
        and "status" in text
        and any(
            word in text
            for word in ("count", "counts", "group", "number")
        )
    ):
        return "status_counts", get_grievance_status_counts()

    # 6. Village counts
    if "village" in text and "grievance" in text:
        return "village_counts", get_village_grievance_counts()

    # 7. Total grievances
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

    # 8. Pending grievances
    if "pending" in text and "grievance" in text:
        return "pending", get_pending_grievances()

    # 9. High-priority resolved grievances
    if (
        "priority" in text
        and any(word in text for word in ("high", "critical"))
        and "resolved" in text
    ):
        return (
            "high_priority_resolved",
            get_high_priority_resolved_grievances(),
        )

    # 10. High-priority grievances
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

    if sql.endswith(";"):
        sql = sql[:-1].strip()

    if not sql:
        raise PermissionError("Empty SQL query.")

    if ";" in sql:
        raise PermissionError(
            "Multiple SQL statements are forbidden."
        )

    # Reject SQL comments.
    if re.search(r"--|#|/\*|\*/", sql):
        raise PermissionError("SQL comments are forbidden.")

    if "?" in sql:
        raise PermissionError(
            "Question-mark placeholders are forbidden."
        )

    if not re.match(r"\ASELECT\b", sql, re.IGNORECASE):
        raise PermissionError("Only SELECT queries are allowed.")

    if re.search(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|"
        r"REPLACE|GRANT|REVOKE|CALL|EXECUTE|INTO|LOAD_FILE|"
        r"SLEEP|BENCHMARK)\b",
        sql,
        re.IGNORECASE,
    ):
        raise PermissionError("Unsafe SQL was blocked.")

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
    Reject joins, unions and subqueries.
    """
    if not mobile_number:
        raise PermissionError(
            "Registered citizen account is unavailable."
        )

    sql = sql.strip().rstrip(";")

    match = re.match(
        r"\ASELECT\b.+?\bFROM\s+`?grievances`?(?=\s|$)",
        sql,
        re.IGNORECASE | re.DOTALL,
    )

    if not match:
        raise PermissionError(
            "Citizens can access only their own grievances."
        )

    if re.search(
        r"\b(JOIN|UNION|INTERSECT|EXCEPT|EXISTS)\b|\bSELECT\b",
        sql[match.end():],
        re.IGNORECASE,
    ):
        raise PermissionError(
            "Complex citizen queries are not permitted."
        )

    select_list = re.split(
        r"\bFROM\b",
        sql,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    if re.search(
        r"\b(citizen_mobile|citizen_email|citizen_name|"
        r"mobile_number|phone_number|email|address)\b",
        select_list,
        re.IGNORECASE,
    ):
        raise PermissionError(
            "Private contact details cannot be displayed."
        )

    remainder = sql[match.end():]

    if remainder.strip() and not re.match(
        r"\s*(WHERE|ORDER\s+BY|GROUP\s+BY|HAVING|LIMIT)\b",
        remainder,
        re.IGNORECASE,
    ):
        raise PermissionError(
            "Additional tables are not permitted."
        )

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

    return (
        safe_sql + " " + trailing_clause.strip()
    ).strip(), (mobile_number,)


# --------------------------------------------------
# HUMAN-READABLE RESPONSE
# --------------------------------------------------

def explain_result(question, result, role):
    """Summarize authorized database results."""
    prompt = f"""
You are a Government Citizen Service AI Assistant.

Rules:
1. Use only the supplied database results.
2. Never invent records, statuses, dates or details.
3. Never reveal passwords, hashes, OTPs, tokens or secrets.
4. Never reveal personal contact details.
5. If there are no results, say no matching records were found.
6. Answer clearly and concisely.
7. Never print raw Python tuples, lists or datetime objects.
8. Do not claim to perform actions that were not performed.
9. User role: {role}

Question:
{question}

Authorized database results:
{result}

Provide a human-readable answer:
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
                    return "No matching records were found."

                lines = ["Your grievances:"]

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
                    stage = get_value(
                        row, "work_stage_code", 4, "N/A"
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
                        f"   Work Progress: {progress}\n"
                        f"   Reported On: {created}"
                    )

                return "\n\n".join(lines)
            
        
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
                return "No grievances were found."

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

                lines.append(
                    f"{index}. {code} - {title} - "
                    f"{status} - {stage} - "
                    f"Work Progress: {progress} - "
                    f"Reported On: {created}"
                )

            return "\n".join(lines)

        # DIRECT DATABASE QUERIES
        direct = build_direct_query(question)

        if direct is not None:
            query_type, result = direct

            if query_type == "grievance_details":
                return format_grievance_details(result)

            if query_type == "street_light_search":
                return format_search_results(result)

            if query_type == "unresolved":
                return format_unresolved_grievances(result)

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
            return "No matching records were found."

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