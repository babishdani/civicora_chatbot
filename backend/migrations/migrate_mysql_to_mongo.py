
import argparse
from datetime import date, datetime, time
from decimal import Decimal

from bson.binary import Binary
from bson.decimal128 import Decimal128
from pymongo import UpdateOne

from db import get_connection
from mongo_db import db, test_connection


BATCH_SIZE = 500

# Only approved, non-sensitive fields are migrated.
# Tables containing citizen records, authentication data,
# private contact information, or operational secrets are excluded.

ALLOWED_TABLES = {
    "activities": {
        "id", "activity_code", "title", "category",
        "activity_date", "location", "description",
        "status", "created_at", "updated_at",
    },
    "activity_photos": {
        "id", "activity_id", "key", "url", "name", "position",
    },
    "blocks": {
        "id", "code", "label", "sort_order", "is_active",
    },
    "constituency_gallery_images": {
        "id", "position", "key", "url", "name",
        "caption_en", "caption_ta", "created_at", "updated_at",
    },
    "grievance_categories": {
        "id", "code", "label", "sort_order", "is_active",
        "enable_livelihood", "enable_updates",
        "enable_citizen_services",
    },
    "grievance_statuses": {
        "id", "code", "label", "sort_order",
        "is_active", "created_at", "updated_at",
    },
    "industrial_sectors": {
        "id", "code", "label", "sort_order", "is_active",
    },
    "job_fair_statuses": {
        "id", "code", "label", "sort_order", "is_active",
    },
    "job_fairs": {
        "id", "job_code", "title", "assumed_date",
        "status_code", "venue", "partners",
        "candidates", "placements", "created_at", "updated_at",
    },
    "panchayats": {
        "id", "code", "label", "sort_order", "is_active", "block_id",
    },
    "placement_streams": {
        "id", "code", "label", "sort_order", "is_active",
    },
    "shg_schemes": {
        "id", "code", "label", "sort_order", "is_active",
    },
    "villages": {
        "id", "code", "label", "sort_order",
        "is_active", "panchayat_id",
    },
}

PRIMARY_KEYS = {
    "activities": "id",
    "activity_photos": "id",
    "blocks": "id",
    "constituency_gallery_images": "id",
    "grievance_categories": "id",
    "grievance_statuses": "id",
    "industrial_sectors": "id",
    "job_fair_statuses": "id",
    "job_fairs": "id",
    "panchayats": "id",
    "placement_streams": "id",
    "shg_schemes": "id",
    "villages": "id",
}


def convert_value(value):
    if isinstance(value, Decimal):
        return Decimal128(value)

    if isinstance(value, datetime):
        return value

    if isinstance(value, (date, time)):
        return value.isoformat()

    if isinstance(value, bytes):
        return Binary(value)

    if isinstance(value, dict):
        return {
            key: convert_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [convert_value(item) for item in value]

    return value


def migrate(dry_run=True):
    connection = None
    cursor = None

    try:
        print(test_connection()["message"])

        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("SHOW TABLES")
        table_rows = cursor.fetchall()
        source_tables = [list(row.values())[0] for row in table_rows]

        print(f"MySQL tables found: {len(source_tables)}")
        print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")

        missing_tables = set(ALLOWED_TABLES) - set(source_tables)

        if missing_tables:
            raise RuntimeError(
                f"Approved tables missing from MySQL: "
                f"{sorted(missing_tables)}"
            )

        total_processed = 0

        for table, allowed_fields in ALLOWED_TABLES.items():
            primary_key = PRIMARY_KEYS[table]

            cursor.execute(f"SHOW COLUMNS FROM `{table}`")
            columns = {row["Field"] for row in cursor.fetchall()}

            if not allowed_fields.issubset(columns):
                missing = allowed_fields - columns
                raise RuntimeError(
                    f"{table} is missing expected columns: {sorted(missing)}"
                )

            if primary_key not in allowed_fields:
                raise RuntimeError(
                    f"Primary key {primary_key} is not allowlisted for {table}"
                )

            selected_fields = sorted(allowed_fields)

            # Column names come only from the static allowlist above.
            column_sql = ", ".join(f"`{field}`" for field in selected_fields)
            cursor.execute(
                f"SELECT {column_sql} FROM `{table}`"
            )

            collection = db[table]

            if not dry_run and collection.count_documents({}) > 0:
                raise RuntimeError(
                    f"MongoDB collection '{table}' is not empty. "
                    "Stopping to prevent accidental overwrites."
                )

            processed = 0

            while True:
                rows = cursor.fetchmany(BATCH_SIZE)

                if not rows:
                    break

                if dry_run:
                    processed += len(rows)
                    continue

                operations = []

                for row in rows:
                    document = {
                        field: convert_value(row[field])
                        for field in selected_fields
                    }

                    document["_id"] = document.pop(primary_key)

                    operations.append(
                        UpdateOne(
                            {"_id": document["_id"]},
                            {"$setOnInsert": document},
                            upsert=True,
                        )
                    )

                if operations:
                    collection.bulk_write(operations, ordered=True)
                    processed += len(operations)

            print(
                f"{'CHECKED' if dry_run else 'MIGRATED'}: {table} | "
                f"Rows: {processed} | "
                f"Approved fields: {len(allowed_fields)}"
            )

            total_processed += processed

        print(f"\nTotal approved rows processed: {total_processed}")

        if dry_run:
            print("Dry run complete. MongoDB data was not modified.")
        else:
            print("Migration complete.")
            print("MySQL source data was not deleted.")

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Safely migrate approved MySQL data to MongoDB."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write approved records to MongoDB. Default is dry-run.",
    )
    args = parser.parse_args()

    migrate(dry_run=not args.execute)
