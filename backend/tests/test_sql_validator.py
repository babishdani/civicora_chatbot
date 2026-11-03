
from sql_validator import validate_sql


tests = [
    (
        "SELECT grievance_code, status_code FROM grievances",
        True,
    ),
    (
        "SELECT COUNT(*) FROM grievances",
        True,
    ),
    (
        "SELECT * FROM grievances",
        False,
    ),
    (
        "DELETE FROM grievances",
        False,
    ),
    (
        "UPDATE users SET role = 'admin'",
        False,
    ),
    (
        "SELECT SLEEP(5)",
        False,
    ),
    (
        "SELECT id FROM users; SELECT id FROM grievances",
        False,
    ),
    (
        "SELECT id FROM grievances -- comment",
        False,
    ),
]

for query, expected in tests:
    result = validate_sql(query)
    status = "PASS" if result == expected else "FAIL"
    print(f"{status}: {query} -> {result}")
