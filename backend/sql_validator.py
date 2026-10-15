
import re

import sqlglot
from sqlglot import exp


FORBIDDEN_FUNCTIONS = {
    "LOAD_FILE",
    "SLEEP",
    "BENCHMARK",
}

# Functions that can modify session state or variables
# are not needed for this chatbot's read-only queries.
FORBIDDEN_OPERATORS = {
    ":=",
}


def validate_sql(sql: str) -> bool:
    """
    Conservatively validate a single, read-only MySQL SELECT query.

    This is a defense-in-depth check, not a replacement
    for backend authorization or database permissions.
    """

    if not isinstance(sql, str):
        return False

    sql = sql.strip()

    if not sql:
        return False

    # Reject SQL comments.
    if re.search(r"--|#|/\*|\*/", sql):
        return False

    # Reject variable assignment.
    if any(operator in sql for operator in FORBIDDEN_OPERATORS):
        return False

    # Permit one optional trailing semicolon only.
    without_trailing = sql.rstrip(";").strip()

    if not without_trailing:
        return False

    if ";" in without_trailing:
        return False

    try:
        statements = sqlglot.parse(
            without_trailing,
            read="mysql",
        )
    except sqlglot.errors.ParseError:
        return False

    # Exactly one valid statement is required.
    if len(statements) != 1 or statements[0] is None:
        return False

    query = statements[0]

    # Only SELECT statements are permitted.
    if not isinstance(query, exp.Select):
        return False

    # Inspect every SELECT, including nested queries and CTEs.
    for select in query.find_all(exp.Select):

        # Reject SELECT * and table.* projections.
        for projection in select.expressions:
            if isinstance(projection, exp.Star):
                return False

            if isinstance(projection, exp.Column) and projection.is_star:
                return False

        # Reject dangerous functions.
        for function in select.find_all(exp.Func):
            function_name = function.sql_name().upper()

            if function_name in FORBIDDEN_FUNCTIONS:
                return False

            if (
                isinstance(function, exp.Anonymous)
                and function.name.upper() in FORBIDDEN_FUNCTIONS
            ):
                return False

    # Reject SELECT INTO and related output clauses.
    if any(
        isinstance(node, exp.Into)
        for node in query.walk()
    ):
        return False

    return True
