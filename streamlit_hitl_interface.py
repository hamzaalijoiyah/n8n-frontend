# streamlit_app.py
import streamlit as st
import requests
from supabase import create_client, Client

st.set_page_config(layout="wide")

# --- Configuration ---
N8N_SUBMIT_WEBHOOK_URL = "https://sumhuman.app.n8n.cloud/webhook-waiting/350"
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

def trigger_n8n_webhook():
    """Triggers the n8n webhook via GET request with auth header."""
    try:
        response = requests.get(N8N_SUBMIT_WEBHOOK_URL, headers=AUTH_HEADER, timeout=20)
        if response.status_code == 200:
            st.success("✅ n8n execution started. Images marked for deletion have been removed.")
            st.balloons()
            return True
        else:
            st.error(f"❌ Failed to trigger n8n. Status Code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        st.error(f"🚨 Error connecting to n8n: {e}")
        return False

@st.cache_data(ttl=300)
def fetch_images_from_supabase(session_id):
    if not session_id:
        return None
    try:
        resp = supabase.table(SUPABASE_TABLE).select("image_url, query").eq("session_id", session_id).order("id").execute()
        if hasattr(resp, 'data') and isinstance(resp.data, list):
            return [
                {'imageUrl': item.get('image_url'), 'query': item.get('query')}
                for item in resp.data
            ]
        return []
    except Exception as e:
        st.error(f"Supabase fetch error: {e}")
        return None

# --- Query Params & Session State Initialization ---
query_params = st.query_params
url_session_id = query_params.get("sessionId")  # No indexing needed in Streamlit ≥1.27
url_query = query_params.get("query", "")

if 'session_id' not in st.session_state:
    st.session_state.session_id = url_session_id
    st.session_state.original_query = url_query
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
    'error_loading': False
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --- Validate Session ID ---
if not st.session_state.get('session_id'):
    st.error("Missing 'sessionId'. Please ensure the link includes '?sessionId=...'")
    st.stop()

st.info(f"Reviewing images for query: \"{st.session_state.original_query}\" (Session: {st.session_state.session_id})")

# --- Load Data From Supabase Once Per Session ---
if st.session_state.session_id and not st.session_state.data_loaded and not st.session_state.error_loading:
    with st.spinner(f"Loading images for session {st.session_state.session_id}..."):
        data = fetch_images_from_supabase(st.session_state.session_id)
        if data is not None:
            st.session_state.all_images_data = data
            st.session_state.current_index = 0
            st.session_state.image_decisions = {i: 'keep' for i in range(len(data))}
            st.session_state.data_loaded = True
            st.success(f"Loaded {len(data)} images.")
            st.rerun()
        else:
            st.session_state.error_loading = True
            st.error("No images found in Supabase for this session.")

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
                st.image(img_url, caption=f"Image {current_idx + 1} (Query: {img_query})", use_column_width=True)
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
        new_prompt = st.text_area("Provide instructions or a query:", value=st.session_state.original_query)
        if st.button("🔄 Request New Images", disabled=st.session_state.submitted or not new_prompt.strip()):
            st.warning("This action requires backend integration.")

elif st.session_state.error_loading:
    st.error("Could not load image data. Please check Supabase connection.")
    new_prompt = st.text_area("Provide instructions or a refined query:", value=st.session_state.original_query)
    if st.button("🔄 Request New Images", disabled=st.session_state.submitted or not new_prompt.strip()):
        st.warning("This action requires backend integration.")

else:
    st.info("Initializing...")

# --- Debug Info ---
with st.expander("Debug Info"):
    st.write("Query Params:", query_params)
    st.write("Session State:", st.session_state)