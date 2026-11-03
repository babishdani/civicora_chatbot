
from db import get_connection
from mongo_db import users_collection

connection = None
cursor = None

try:
    # Connect to MySQL
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    # Fetch only citizen accounts
    cursor.execute("""
        SELECT id, role, mobile_number, is_active
        FROM users
        WHERE role = 'citizen'
    """)

    users = cursor.fetchall()

    migrated_count = 0

    for user in users:
        user_document = {
            "_id": str(user["id"]),
            "mysql_id": int(user["id"]),
            "mobile_number": user["mobile_number"],
            "role": user["role"],
            "is_active": bool(user["is_active"]),
        }

        # Upsert prevents duplicate records on reruns
        users_collection.replace_one(
            {"_id": str(user["id"])},
            user_document,
            upsert=True,
        )

        migrated_count += 1

    print("Migration completed!")
    print("MySQL citizen records:", len(users))
    print("MongoDB records migrated:", migrated_count)
    print(
        "MongoDB citizen count:",
        users_collection.count_documents({"role": "citizen"})
    )

except Exception as error:
    print("Migration failed:", type(error).__name__, str(error))

finally:
    if cursor:
        cursor.close()

    if connection:
        connection.close()
