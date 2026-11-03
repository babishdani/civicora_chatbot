
import re


OUT_OF_SCOPE_REPLY = (
    "Sorry, I can only help with Ottapidaram citizen services "
    "and related website information. Please contact our support "
    "team at +91 8870556215 for further assistance."
)


def classify_question(question: str) -> str:
    if not isinstance(question, str):
        return "out_of_scope"

    text = re.sub(r"\s+", " ", question.strip().lower())

    if not text:
        return "out_of_scope"

    # 1. Greetings
    if re.fullmatch(
        r"(hi|hello|hey|vanakkam|good morning|good afternoon|"
        r"good evening|thanks|thank you|nandri)[!. ]*",
        text,
    ):
        return "greeting"

    # 2. Grievance queries
    grievance_terms = (
        "grievance", "grievances",
        "complaint", "complaints",
        "petition", "petitions",
        "case status", "my case", "my cases",
        "application status", "my application",
        "my applications", "my issue", "my issues",
        "my problem", "my problems",
        "my request", "my requests",
        "my report", "my reports",
        "track my complaint", "track my grievance",
        "track my petition", "track my application",
        "check my complaint", "check my grievance",
        "check my petition",
        "status of my complaint", "status of my grievance",
        "status of my petition",
        "action taken on my complaint",
        "action taken on my petition",
        "any update on my complaint",
        "any update on my petition",
        "manu", "manukkal", "pugaar", "pugar",
        "en manu", "en pugaar", "en complaint",
        "en petition", "en grievance", "en case",
        "en application", "ennoda manu",
        "ennoda complaint", "ennoda petition",
        "ennoda grievance", "ennoda case",
        "ennoda application", "manu status",
        "manu enna aachu", "complaint enna aachu",
        "petition enna aachu", "status enna",
    )

    if any(term in text for term in grievance_terms):
        return "grievance"

    # 3. Supported public database services
    public_terms = {
        "blood_donors": (
            "blood donor", "blood donors",
            "blood donation", "find a donor",
            "find donors", "available donor",
            "available donors", "blood group",
        ),
        "job_fairs": (
            "job fair", "job fairs",
            "jobfair", "jobfairs",
        ),
        "activities": (
            "activity", "activities",
            "public event", "public events",
            "upcoming event", "upcoming events",
            "program", "programs",
        ),
    }

    for category, terms in public_terms.items():
        if any(term in text for term in terms):
            return category

    # 4. Explicit website and citizen-service guidance
    website_terms = (
        "ottapidaram website",
        "official website",
        "citizen portal",
        "citizen services",
        "website services",
        "how to use this website",
        "how do i use the website",
        "website login",
        "portal login",
        "how to register",
        "registration process",
        "contact support",
        "support contact",
    )

    if any(term in text for term in website_terms):
        return "website"

    # 5. Everything else is out of scope
    return "out_of_scope"

