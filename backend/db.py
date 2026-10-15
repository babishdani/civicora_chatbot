
import mysql.connector

from config import DB_CONFIG
from privacy import sanitize_result


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
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(query, params or ())

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

        conn.commit()
        return {"message": "Success"}

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()
