
import re


RESTRICTED_TERMS = [
    r"\bpasswords?\b",
    r"\blogin_password\b",
    r"\bpassword_hash\b",
    r"\botps?\b",
    r"\botp_hash\b",
    r"\brefresh_tokens?\b",
    r"\baccess_tokens?\b",
    r"\bsecret_keys?\b",
    r"\bcredentials?\b",
]


def can_access(role, question):
    if not isinstance(role, str):
        return False

    if not isinstance(question, str):
        return False

    role = role.strip().lower()
    question = question.strip().lower()

    if not role or not question:
        return False

    # Reject unknown roles.
    if role not in {"admin", "commander", "citizen"}:
        return False

    # Block credential-related requests for every role.
    for pattern in RESTRICTED_TERMS:
        if re.search(pattern, question, re.IGNORECASE):
            return False

    # Admin: application-data access, subject to
    # backend authorization and SQL validation.
    if role == "admin":
        return True

    # Commander: operational data, including contact
    # details, but never authentication credentials.
    if role == "commander":
        return True

    # Citizen: this checks only the question-level gate.
    # Ownership MUST be enforced in chatbot.py/backend.
    if role == "citizen":
        return True

    return False
