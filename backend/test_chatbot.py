
from chatbot import (
    ask_database,
    detect_civicora_service,
    build_service_response,
)

# -----------------------------------
# TEST 1: Children Support Routing
# -----------------------------------
question = "I need help with children support"

print("\n--- TEST 1: SERVICE ROUTING ---")

service = detect_civicora_service(question)

print("Question:", question)
print("Detected service:", service)

if service:
    print("Response:")
    print(build_service_response(service, question))
else:
    print("NO SERVICE DETECTED")


# -----------------------------------
# TEST 2: Existing Chatbot Function
# -----------------------------------
print("\n--- TEST 2: DATABASE CHATBOT ---")

question = "Show all grievances"

answer = ask_database(question)

print("Question:", question)
print("\nAnswer:")
print(answer)
