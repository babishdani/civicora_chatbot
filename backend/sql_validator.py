
import re

import sqlglot
from sqlglot import exp


FORBIDDEN_FUNCTIONS = {
    "LOAD_FILE",
    "SLEEP",
    "BENCHMARK",
}

FORBIDDEN_OPERATORS = {
    ":=",
}


def validate_sql(sql: str) -> bool:
    """
    Validate a single read-only MySQL SELECT query.

    This is a defense-in-depth check.
    Database permissions and backend authorization
    are still required.
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

    # Permit one optional trailing semicolon.
    if sql.endswith(";"):
        sql = sql[:-1].strip()

    # Reject multiple SQL statements.
    if not sql or ";" in sql:
        return False

    try:
        # sqlglot may not understand MySQL driver's %s placeholders.
        # # Replace placeholders only in a temporary copy used for parsing.

        sql_for_validation = re.sub(
            r"%s",
            "NULL",
            sql,
        )

        statements = sqlglot.parse(
            sql_for_validation,
            read="mysql",
        )
    except Exception:
        return False

    # Exactly one valid statement is required.
    if len(statements) != 1 or statements[0] is None:
        return False

    query = statements[0]

    # Allow only SELECT statements.
    if not isinstance(query, exp.Select):
        return False

    # Reject SELECT INTO clauses.
    if any(
        isinstance(node, exp.Into)
        for node in query.walk()
    ):
        return False

    # Reject locking SELECT statements.
    if any(
        isinstance(node, exp.Lock)
        for node in query.walk()
    ):
        return False

    # Reject SELECT * and table.* projections.
    for select in query.find_all(exp.Select):
        for projection in select.expressions:
            if isinstance(projection, exp.Star):
                return False

            if (
                isinstance(projection, exp.Column)
                and projection.is_star
            ):
                return False

    # Reject dangerous functions.
    for function in query.find_all(exp.Func):
        function_name = function.sql_name().upper()

        if function_name in FORBIDDEN_FUNCTIONS:
            return False

        if (
            isinstance(function, exp.Anonymous)
            and function.name.upper() in FORBIDDEN_FUNCTIONS
        ):
            return False

    return True
