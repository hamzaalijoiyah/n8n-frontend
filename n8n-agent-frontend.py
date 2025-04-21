import streamlit as st
import requests
import uuid

# Constants
WEBHOOK_URL = "https://hamzaalijoiyah.app.n8n.cloud/webhook/3b0e1f5f-3a95-438a-aafe-442270633997"
# Set the header name to match your n8n Header Auth credential configuration
N8N_HEADER_NAME = "Authorization"
# Use Streamlit secrets to get the header value securely
# Ensure you add this secret in the Streamlit Cloud settings for your app
try:
    N8N_HEADER_VALUE = st.secrets["N8N_HEADER_VALUE"]
except KeyError:
    st.error("Error: N8N_HEADER_VALUE secret not found. Please configure secrets in Streamlit Cloud.")
    st.stop() # Stop execution if secret is missing

def generate_session_id():
    return str(uuid.uuid4())

# Modified function to trigger the n8n workflow asynchronously
def trigger_llm_processing(session_id, message):
    headers = {
        N8N_HEADER_NAME: N8N_HEADER_VALUE, # Use the secret value
        "Content-Type": "application/json"
    }
    payload = {
        "sessionId": session_id,
        "chatInput": message
    }

    # Debug information
    print("Request URL:", WEBHOOK_URL)
    print("Headers:", headers)
    print("Payload:", payload)

    try:
        # Send the request to n8n. We expect an immediate response.
        # Set a shorter timeout as we don't expect a long wait here.
        response = requests.post(WEBHOOK_URL, json=payload, headers=headers, timeout=30) # 30 seconds timeout

        # Debug response
        print("Response Status:", response.status_code)
        print("Response Headers:", dict(response.headers))
        print("Response Body (first 500 chars):", response.text[:500])

        # Check if the webhook acknowledged the request successfully (e.g., 200 OK or 202 Accepted)
        # Adjust status codes based on what your n8n "Respond to Webhook" node returns
        if response.status_code in [200, 202]:
            print("Successfully triggered n8n workflow.")
            # Return a message to display to the user
            return "Your request has been received and is being processed. The result will be added to the authorized Google Sheet shortly."
        else:
            # Handle unexpected status codes from the initial webhook response
            print(f"Error: Received unexpected status code {response.status_code} from n8n webhook.")
            return f"Error: Failed to trigger the agent. Status code: {response.status_code}"

    except requests.exceptions.Timeout:
        print("Error: Request to n8n webhook timed out.")
        return "Error: The connection to the agent webhook timed out. Please try again."
    except requests.exceptions.RequestException as e:
        print(f"Error: Request failed: {e}")
        return f"Error: Could not connect to the agent webhook. {e}"


def main():
    st.title("Chat with Sumhuman AI")

    # Initialize session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        st.session_state.session_id = generate_session_id()
        print(f"New Session ID generated: {st.session_state.session_id}") # Add log for session ID

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # User input
    user_input = st.chat_input("Type your message here...")

    if user_input:
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        # Trigger the LLM processing asynchronously
        # Display a temporary "processing" message
        with st.chat_message("assistant"):
            with st.spinner("Sending request to agent..."):
                 confirmation_message = trigger_llm_processing(st.session_state.session_id, user_input)

            # Add the confirmation/error message to chat history
            st.session_state.messages.append({"role": "assistant", "content": confirmation_message})
            # Re-run to display the new message immediately
            st.rerun()


if __name__ == "__main__":
    main()
