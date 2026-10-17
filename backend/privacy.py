# Credentials must NEVER be exposed to any role.
ALWAYS_SENSITIVE_COLUMNS = {
    "password",
    "login_password",
    "password_hash",
    "otp",
    "access_token",
    "secret_key",
}

# Private contact details.
PRIVATE_COLUMNS = {
    "citizen_mobile",
    "citizen_email",
    "mobile_number",
    "phone_number",
    "email",
}


def sanitize_result(result, columns=None, role="citizen"):

    if not result:
        return []

    # Prevent returning unsanitized data.
    if not columns:
        raise ValueError(
            "Cannot sanitize query results without column names."
        )

    role = str(role).lower().strip()

    # Only admin can view permitted contact details.
    show_private_details = False

    protected_indexes = []

    for index, column in enumerate(columns):
        column_name = str(column).lower().strip()

        if column_name in ALWAYS_SENSITIVE_COLUMNS:
            protected_indexes.append(index)

        elif (
            column_name in PRIVATE_COLUMNS
            and not show_private_details
        ):
            protected_indexes.append(index)

    cleaned = []

    for row in result:
        row = list(row)

        for index in protected_indexes:
            if index < len(row):
                row[index] = "[PROTECTED]"

        cleaned.append(tuple(row))

    return cleaned