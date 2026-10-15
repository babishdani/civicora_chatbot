import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Citizen Service AI",
    page_icon="🤖",
    layout="wide"
)

# -------------------------
# SESSION STATE
# -------------------------

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "messages" not in st.session_state:
    st.session_state.messages = []

if "user" not in st.session_state:
    st.session_state.user = None

if "access_token" not in st.session_state:
    st.session_state.access_token = None


# -------------------------
# LOGIN PAGE
# -------------------------

if not st.session_state.logged_in:

    st.title("🤖 Citizen Service AI Assistant")
    st.write("Login to access Citizen Services.")

    mobile = st.text_input("Mobile Number")

    password = st.text_input(
        "Password",
        type="password"
    )

    role = st.selectbox(
        "Role",
        ["citizen", "commander", "admin"]
    )

    if st.button("Login"):

        if not mobile.strip() or not password:
            st.error("Please enter your mobile number and password.")

        else:
            payload = {
                "mobile_number": mobile.strip(),
                "password": password,
                "role": role
            }

            try:
                response = requests.post(
                    f"{API_URL}/login",
                    json=payload,
                    timeout=30
                )

                data = response.json()

                if response.ok and data.get("success"):

                    token = data.get("access_token")

                    if not token:
                        st.error(
                            "Login response has no access token. "
                            "Backend JWT setup is not complete."
                        )

                    else:
                        st.session_state.access_token = token

                        st.session_state.user = {
                            "user_id": data.get("user_id"),
                            "role": data.get("role")
                        }

                        st.session_state.logged_in = True
                        st.session_state.messages = []

                        st.rerun()

                else:
                    st.error(
                        data.get("message", "Invalid login credentials.")
                    )

            except requests.RequestException:
                st.error("Cannot connect to the backend API.")

            except ValueError:
                st.error("Backend returned an invalid response.")


# -------------------------
# CHAT PAGE
# -------------------------

else:

    user = st.session_state.user

    st.title("🤖 Citizen Chatbot")

    st.success(f"Logged in as {user['role']}")

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    question = st.chat_input("Ask your question...")

    if question:

        st.session_state.messages.append({
            "role": "user",
            "content": question
        })

        with st.chat_message("user"):
            st.write(question)

        answer = ""

        try:
            headers = {
                "Authorization": (
                    f"Bearer {st.session_state.access_token}"
                )
            }

            response = requests.post(
                f"{API_URL}/chat",
                json={"question": question},
                headers=headers,
                timeout=120
            )

            data = response.json()

            if response.status_code in (401, 403):
                answer = "Session expired or access denied. Please log in again."

            elif data.get("success"):
                answer = data.get("answer", "No response received.")

            else:
                answer = data.get(
                    "answer",
                    data.get("message", "Request failed.")
                )

        except requests.Timeout:
            answer = "The request timed out. Please try again."

        except requests.RequestException:
            answer = "Cannot connect to the backend API."

        except ValueError:
            answer = "Backend returned an invalid response."

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer
        })

        with st.chat_message("assistant"):
            st.write(answer)

    st.divider()

    if st.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.session_state.access_token = None
        st.session_state.messages = []

        st.rerun()