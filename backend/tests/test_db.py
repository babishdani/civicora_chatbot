from db import execute_query

result = execute_query(
    "SELECT grievance_code, title FROM grievances LIMIT 5"
)

print(result)