
import mysql.connector

from config import DB_CONFIG
from privacy import sanitize_result
from sql_validator import validate_sql


def get_connection():
    return mysql.connector.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        ssl_disabled=False,
        ssl_verify_cert=False,
    )


def execute_query(query, params=None, role="citizen"):
    conn = None
    cursor = None

    try:
        # Validate SQL before opening a database cursor.
        if not validate_sql(query):
            print("SQL VALIDATION FAILED")
            print("Query received:", repr(query))

            raise PermissionError(
                "Unsafe or invalid SQL query was blocked."
            )

        conn = get_connection()
        cursor = conn.cursor()

        # Execute using parameterized values.
        cursor.execute(query, params or ())

        # Return results for SELECT queries.
        if cursor.description is not None:
            rows = cursor.fetchall()

            columns = [
                column[0]
                for column in cursor.description
            ]

            return sanitize_result(
                rows,
                columns,
                role=role,
            )

        # Do not allow non-result queries.
        raise PermissionError(
            "Only read-only SELECT queries are allowed."
        )

    except Exception:
        if conn is not None and conn.is_connected():
            conn.rollback()
        raise

    finally:
        if cursor is not None:
            cursor.close()

        if conn is not None and conn.is_connected():
            conn.close()

def get_citizen_mobile_for_auth(user_id):
    """Internal lookup for an authenticated citizen."""
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

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
            return None

        return str(row[0]).strip()

    finally:
        if cursor is not None:
            cursor.close()

        if conn is not None and conn.is_connected():
            conn.close()
