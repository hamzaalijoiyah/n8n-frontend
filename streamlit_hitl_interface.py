# streamlit_app.py
import streamlit as st
import requests
from supabase import create_client, Client

st.set_page_config(layout="wide")

# --- Configuration ---
N8N_REPROMPT_WEBHOOK_URL = "https://sumhuman.app.n8n.cloud/webhook/3b0e1f5f-3a95-438a-aafe-442270633997"
try:
    N8N_HEADER_VALUE = st.secrets["N8N_HEADER_VALUE"]
except KeyError:
    st.error("Error: N8N_HEADER_VALUE secret not found. Please configure secrets in Streamlit Cloud.")
    st.stop() # Stop execution if secret is missing
AUTH_HEADER = {"Authorization": N8N_HEADER_VALUE}  # Auth header for n8n

# Supabase credentials from secrets.toml
try:
    SUPABASE_URL = st.secrets["supabase"]["url"]
    SUPABASE_KEY = st.secrets["supabase"]["key"]
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"Supabase secrets error: {e}. Configure SUPABASE_URL/KEY in Streamlit secrets.")
    st.stop()

SUPABASE_TABLE = "image_staging_for_review"

# --- Helper Functions ---

def delete_images_from_supabase(session_id, image_urls):
    """Deletes specific images from Supabase."""
    if not session_id or not image_urls:
        st.warning("No session ID or image URLs provided for deletion.")
        return False
    
    try:
        # Ensure exact column name matches Supabase table (e.g., "imageUrl")
        column_name = "image_url"  # ← Verify this matches your Supabase column name
        
        # Debug: Log URLs being deleted
        st.write("Deleting URLs:", image_urls)
        
        # Execute deletion
        result = (
            supabase.table(SUPABASE_TABLE)
            .delete()
            .eq("session_id", session_id)
            .in_(column_name, image_urls)
            .execute()
        )
        
        # Check if deletion succeeded AND affected rows
        if hasattr(result, 'data') and isinstance(result.data, list):
            deleted_count = len(result.data)
            if deleted_count > 0:
                st.success(f"{deleted_count} image(s) deleted from Supabase.")
                return True
            else:
                st.error("No images matched the deletion criteria. Check column names and URL formats.")
                return False
        else:
            st.error("Supabase deletion failed: Invalid response format.")
            return False
            
    except Exception as e:
        st.error(f"Error deleting images: {e}")
        import traceback
        st.exception(traceback.format_exc())
        return False

# --- New Function ---
def delete_all_images_for_session(session_id):
    """Deletes ALL images from Supabase for a given session ID."""
    if not session_id:
        st.warning("No session ID provided for deletion.")
        return False
    try:
        st.write(f"Attempting to delete all images for session: {session_id}")
        result = (
            supabase.table(SUPABASE_TABLE)
            .delete()
            .eq("session_id", session_id)
            .execute()
        )
        # Check if deletion succeeded (even if 0 rows were affected, it's not an error)
        if hasattr(result, 'data'):
            deleted_count = len(result.data) if isinstance(result.data, list) else 0
            st.success(f"{deleted_count} existing image record(s) deleted from Supabase for session {session_id}.")
            return True
        else:
            st.error("Supabase deletion failed: Invalid response format.")
            return False
    except Exception as e:
        st.error(f"Error deleting all images for session {session_id}: {e}")
        import traceback
        st.exception(traceback.format_exc())
        return False
# --- End New Function ---


def trigger_n8n_webhook():
    """Triggers the n8n webhook (resume URL) via GET request with auth header.
    Returns True if successful (200) or if a 409 Conflict occurs (workflow not waiting, which is acceptable for reprompt).
    Returns False for other errors.
    """
    resume_url = st.session_state.get('resume_url')
    if not resume_url:
        st.error("❌ Resume URL is missing. Cannot trigger n8n.")
        return False
    try:
        response = requests.get(resume_url, headers=AUTH_HEADER, timeout=20) # Use resume_url from session state
        if response.status_code == 200:
            st.success("✅ n8n execution resumed/confirmed active using the resume URL.")
            # Consider removing balloons if it's just confirming activity
            # st.balloons() 
            return True
        elif response.status_code == 409:
            # Handle 409 Conflict specifically: Inform user but allow process to continue
            st.info("ℹ️ Could not resume n8n workflow via resume URL (Status 409 - Conflict). This likely means the workflow was not in a waiting state. Proceeding with reprompt.")
            return True # Treat 409 as non-blocking for the reprompt sequence
        else:
            # Handle other non-200 errors
            st.error(f"❌ Failed to trigger n8n resume URL. Status Code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        st.error(f"🚨 Error connecting to n8n resume URL: {e}")
        return False

def trigger_reprompt_webhook(session_id, prompt, user_email): # Add user_email parameter
    """Triggers the n8n reprompt webhook via POST request with auth header."""
    if not session_id or not prompt:
        st.warning("Session ID or prompt missing for reprompting.")
        return False
    # Optional: Add check for user_email if it's strictly required
    # if not user_email:
    #     st.warning("User email missing for reprompting.")
    #     return False
    headers = {
        **AUTH_HEADER, # Include authorization header
        "Content-Type": "application/json"
    }
    payload = {
        "sessionId": session_id,
        "chatInput": prompt,  # Sends the new prompt under the key "chatInput"
        "email": user_email # Add user email to the payload
    }
    try:
        response = requests.post(N8N_REPROMPT_WEBHOOK_URL, json=payload, headers=headers, timeout=30)

        # Check status code first
        if response.status_code == 200:
            try:
                # Attempt to parse JSON response
                response_data = response.json()
                # Check for specific success indicators in the response body
                # MUST have status 200 AND (status:success OR message:Workflow was started)
                if response_data.get("status") == "success" or response_data.get("message") == "Workflow was started":
                    st.success("✅ Reprompt request acknowledged successfully by n8n.")
                    return True
                else:
                    # Got a 200 OK, but the body indicates a different message or failure
                    error_message = response_data.get("message", "Reprompt webhook returned 200 OK but response body did not indicate expected success.")
                    st.error(f"❌ Reprompt failed (n8n response): {error_message}")
                    return False
            except requests.exceptions.JSONDecodeError:
                # Got a 200 OK, but the response wasn't valid JSON - Treat as failure
                st.error("❌ Reprompt failed: Webhook returned success status (200) but response body was not valid JSON.")
                return False
            except Exception as e:
                # Other potential errors processing the response
                st.error(f"❌ Error processing reprompt response: {e}")
                return False
        else:
            # Status code indicates an error
            st.error(f"❌ Failed to trigger reprompt webhook. Status Code: {response.status_code} - {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        st.error(f"🚨 Error connecting to reprompt webhook: {e}")
        return False

@st.cache_data(ttl=300)
def fetch_images_from_supabase(session_id):
    """Fetches images and the associated query from Supabase for a given session ID."""
    if not session_id:
        return None, None  # Return None for both images and query
    try:
        resp = supabase.table(SUPABASE_TABLE).select("image_url, query").eq("session_id", session_id).order("id").execute()
        if hasattr(resp, 'data') and isinstance(resp.data, list) and resp.data:
            images_data = [
                {'imageUrl': item.get('image_url'), 'query': item.get('query')}
                for item in resp.data
            ]
            # Assuming all images in the session have the same query, take it from the first item
            query = resp.data[0].get('query', '') 
            return images_data, query
        return [], None # Return empty list and None query if no data
    except Exception as e:
        st.error(f"Supabase fetch error: {e}")
        return None, None

# --- Query Params & Session State Initialization ---
query_params = st.query_params
url_session_id = query_params.get("sessionId")
url_resume_url = query_params.get("resumeUrl") # Get resumeUrl from query params
url_user_email = query_params.get("user_email") # Get user_email from query params

if 'session_id' not in st.session_state:
    st.session_state.session_id = url_session_id
    st.session_state.resume_url = url_resume_url # Store resumeUrl in session state
    st.session_state.user_email = url_user_email # Store user_email in session state
    st.session_state.current_index = 0
    st.session_state.image_decisions = {}
    st.session_state.submitted = False
    st.session_state.all_images_data = []
    st.session_state.data_loaded = False
    st.session_state.error_loading = False
    if url_session_id:
        fetch_images_from_supabase.clear()

for key, default in {
    'current_index': 0,
    'image_decisions': {},
    'submitted': False,
    'all_images_data': [],
    'original_query': "",
    'data_loaded': False,
    'error_loading': False,
    'resume_url': None, # Add resume_url to session state defaults
    'user_email': None # Add user_email to session state defaults
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --- Validate Session ID, Resume URL, and User Email ---
if not st.session_state.get('session_id'):
    st.error("Missing 'sessionId'. Please ensure the link includes '?sessionId=...'")
    st.stop()

if not st.session_state.get('resume_url'):
    st.error("Missing 'resumeUrl'. Please ensure the link includes '&resumeUrl=...'")
    st.stop() # Stop if resumeUrl is crucial

if not st.session_state.get('user_email'):
    st.warning("Missing 'user_email' query parameter. Reprompting might require it.")
    # Decide if you want to st.stop() here or just warn

# Display Session ID, Query, and Email prominently
st.subheader("Image Review Session")
col_info1, col_info2, col_info3 = st.columns(3) # Added a third column for email
with col_info1:
    st.metric("Session ID", st.session_state.session_id)
with col_info2:
    st.metric("Original Query", st.session_state.original_query if st.session_state.original_query else "N/A")
with col_info3: # Display User Email
    st.metric("User Email", st.session_state.user_email if st.session_state.user_email else "N/A")
st.divider()

# --- Load Data From Supabase Once Per Session ---
if st.session_state.session_id and not st.session_state.data_loaded and not st.session_state.error_loading:
    with st.spinner(f"Loading images for session {st.session_state.session_id}..."):
        images_data, fetched_query = fetch_images_from_supabase(st.session_state.session_id)
        if images_data is not None:
            st.session_state.all_images_data = images_data
            st.session_state.original_query = fetched_query if fetched_query else "Query not found"
            st.session_state.current_index = 0
            st.session_state.image_decisions = {i: 'keep' for i in range(len(images_data))}
            st.session_state.data_loaded = True
            st.success(f"Loaded {len(images_data)} images.")
            st.rerun()
        else:
            st.session_state.error_loading = True
            st.session_state.original_query = "Error loading query"
            st.error("Failed to load image data from Supabase for this session.")
            # Optionally rerun or stop if loading fails critically
            # st.rerun()

# --- Main Review UI ---
if st.session_state.data_loaded:
    if st.session_state.submitted:
        st.success("Review has been submitted. You can close this page.")
        st.stop()

    images = st.session_state.all_images_data
    total_images = len(images)

    if total_images > 0:
        st.subheader(f"Reviewing Image {st.session_state.current_index + 1} of {total_images}")
        current_idx = st.session_state.current_index
        img_url = images[current_idx].get('imageUrl', '')
        img_query = images[current_idx].get('query', 'N/A')

        col1, col2 = st.columns([2, 1])
        with col1:
            if img_url:
                # Use use_container_width instead of the deprecated use_column_width
                st.image(img_url, caption=f"Image {current_idx + 1}", use_container_width=True)
            else:
                st.warning("Image URL missing.")

        with col2:
            current_decision = st.session_state.image_decisions.get(current_idx, 'keep')
            decision = st.radio(
                "Keep or Delete?",
                ('Keep', 'Delete'),
                index=0 if current_decision == 'keep' else 1,
                key=f"decision_{current_idx}",
                label_visibility="collapsed"
            )
            if decision.lower() != current_decision:
                st.session_state.image_decisions[current_idx] = decision.lower()
                st.rerun()

            st.markdown("---")
            prev_disabled = current_idx == 0
            next_disabled = current_idx == total_images - 1
            prev_col, next_col = st.columns(2)
            with prev_col:
                if st.button("⬅️ Previous", disabled=prev_disabled):
                    st.session_state.current_index -= 1
                    st.rerun()
            with next_col:
                if st.button("Next ➡️", disabled=next_disabled):
                    st.session_state.current_index += 1
                    st.rerun()

            st.markdown("---")
            kept_count = sum(1 for d in st.session_state.image_decisions.values() if d == 'keep')
            st.metric("Images Marked 'Keep'", kept_count)
            st.metric("Images Marked 'Delete'", total_images - kept_count)

        # --- Final Actions ---
        st.markdown("---")
        st.subheader("Final Actions")
        if st.button("✅ Submit Review (Delete Selected)", key="continue_button", type="primary", disabled=st.session_state.submitted):
            deleted_urls = [
                images[i]['imageUrl'] for i, d in st.session_state.image_decisions.items()
                if d == 'delete' and i < len(images) and images[i].get('imageUrl')
            ]

            if deleted_urls:
                if not delete_images_from_supabase(st.session_state.session_id, deleted_urls):
                    st.error("Failed to delete images from Supabase.")
                    st.stop()

            # Trigger n8n workflow
            if trigger_n8n_webhook():
                st.session_state.submitted = True
                fetch_images_from_supabase.clear()
                st.rerun()

    elif not st.session_state.error_loading:
        st.warning("No images found in Supabase for this session.")
        # Removed the old placeholder button here

elif st.session_state.error_loading:
    st.error("Could not load image data. Please check Supabase connection.")
    # Removed the old placeholder button here

else:
    st.info("Initializing...")

# --- Reprompt Section --- (Always visible unless submitted)
st.divider()
st.subheader("Reprompt Agent")
if not st.session_state.submitted:
    new_prompt = st.text_area("Provide new instructions or a refined query:", value=st.session_state.original_query, key="reprompt_text_area")
    if st.button("🔄 Send New Prompt to Agent", key="reprompt_button", disabled=not new_prompt.strip()):
        session_id = st.session_state.session_id
        user_email = st.session_state.user_email # Get email from session state

        # Step 1: Delete all existing images for the session
        st.info("Deleting existing images...")
        if delete_all_images_for_session(session_id):
            st.success("Existing images cleared.")
            
            # Step 2: Trigger the resume URL to ensure n8n is active
            st.info("Ensuring n8n workflow is active...")
            if trigger_n8n_webhook(): # Use the existing function that hits the resumeUrl
                st.success("n8n workflow resumed/active.")

                # Step 3: Send the new prompt
                st.info("Sending new prompt...")
                # Pass user_email to the function call
                if trigger_reprompt_webhook(session_id, new_prompt, user_email):
                    # Clear relevant state and cache, then rerun to show loading/wait state
                    st.info("Reprompt sent. Clearing current view and waiting for new images...")
                    st.session_state.all_images_data = []
                    st.session_state.current_index = 0
                    st.session_state.image_decisions = {}
                    st.session_state.data_loaded = False # Force reload
                    st.session_state.error_loading = False
                    fetch_images_from_supabase.clear() # Clear cache
                    st.rerun() # Rerun to reflect state changes and trigger loading spinner
                else:
                    st.error("Failed to send the new prompt.") # Error specific to reprompt webhook
            else:
                st.error("Failed to trigger the n8n resume URL. Reprompt aborted.") # Error specific to resume webhook
        else:
            st.error("Failed to delete existing images. Reprompt aborted.") # Error specific to deletion

elif st.session_state.submitted:
    st.info("Review already submitted. Reprompting is disabled.")

# --- Debug Info ---
with st.expander("Debug Info"):
    st.write("Query Params:", query_params)
    st.write("Session State:", st.session_state)