import streamlit as st
import logging
import re
import uuid
import base64
import json
import os
from src.utils import parse_s3_uri, query_agent, s3_get_object, s3_head_object, save_feedback, AGENT_ID, AGENT_ALIAS_ID, AGENT_SEARCH_ID, AGENT_SEARCH_ALIAS_ID
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------------------------------------------------
# ¦ GROUP-BASED AUTHORIZATION
# Allowed groups are set via the ALLOWED_COGNITO_GROUPS environment variable (comma-separated),
# injected by the ECS task definition in prometheon-workload-jouleverne-dev.
# The ALB (authenticate-oidc) has already verified the JWT signature. We only decode the payload
# to read the cognito:groups claim from the x-amzn-oidc-accesstoken header.
# ---------------------------------------------------------------------------------------------------------------------
_allowed_groups = set(
    g.strip() for g in os.environ.get("ALLOWED_COGNITO_GROUPS", "").split(",") if g.strip()
)

def _get_cognito_groups() -> set:
    try:
        access_token = st.context.headers.get("x-amzn-oidc-accesstoken", "")
        if not access_token:
            return set()
        payload_b64 = access_token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return set(payload.get("cognito:groups", []))
    except Exception:
        return set()

if _allowed_groups and not (_get_cognito_groups() & _allowed_groups):
    st.error("403 - Access Denied: you are not authorised to access this application.")
    st.stop()


# Initialize sources in session state (only last answer's sources are kept)
if "s3_refs" not in st.session_state:
      st.session_state["s3_refs"] = []
if "web_refs" not in st.session_state:
      st.session_state["web_refs"] = []

# Bucket names
BUCKET_EXTRACTED_TEXT = "prometheon-joule-verne-bfe-extracted-text-dev"
BUCKET_PDF = "prometheon-joule-verne-bfe-public-data-pdf-dev"
BUCKET_WEBSITE = "prometheon-joule-verne-bfe-website-content-dev"

session_id = st.session_state.get("session_id", str(uuid.uuid4()))
st.session_state["session_id"] = session_id

if "messages" not in st.session_state:
      st.session_state.messages = []

col1, col2 = st.columns([1,8])

with col1:
      st.markdown(" ") 
      st.image("./img/bundesamt_logo.jpeg", width=60)

with col2:
      st.title("Demo BFE - Chatbot :zap:")

st.caption("🔒 Your interactions are logged to help us improve this chatbot.")

with st.expander(":information_source: :construction:"):
    st.write("""
    This is a demo application and will still be submitted to changes. The chatbot might not always be correct or precise. Do not hesitate to check the sources in the side bar if unsure. Please be careful not to upload any personal data in the chat.
    For any questions or requests you can [contact us](mailto:digitalisierung@bfe.admin.ch) at the Digital Innovation & Geoinformation section :blush:
    """)

for idx, message in enumerate(st.session_state.messages):
      with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                  feedback_key = f"feedback_{idx}"
                  score = st.feedback("thumbs", key=feedback_key)
                  if score is not None and st.session_state.get(f"{feedback_key}_saved") != score:
                        # Find the preceding user message
                        user_query = ""
                        for prev in range(idx - 1, -1, -1):
                              if st.session_state.messages[prev]["role"] == "user":
                                    user_query = st.session_state.messages[prev]["content"]
                                    break
                        rating = "positive" if score == 1 else "negative"
                        agent_variant = "web_search" if st.session_state.get("web_search_enabled", False) else "default"
                        save_feedback(
                              session_id=st.session_state["session_id"],
                              message_index=idx,
                              rating=rating,
                              user_query=user_query,
                              agent_response=message["content"],
                              agent_variant=agent_variant,
                        )
                        st.session_state[f"{feedback_key}_saved"] = score

st.sidebar.write("**Settings**  :pushpin:")

# Web search toggle — disabled once conversation has started
has_messages = len(st.session_state.get("messages", [])) > 0

# Initialize toggle key to match web_search_enabled state
if "web_search_toggle_value" not in st.session_state:
      st.session_state["web_search_toggle_value"] = st.session_state.get("web_search_enabled", False)

web_search_toggle = st.sidebar.toggle(
      "🔍 Enable web search",
      key="web_search_toggle_value",
      disabled=has_messages,
      help="Enables web search for current news and events. Can only be selected before the first message."
)

# Confirmation dialog when user enables web search
if web_search_toggle and not st.session_state.get("web_search_enabled", False) and not st.session_state.pop("web_search_cancelled", False):
      @st.dialog("⚠️ Enable web search?")
      def confirm_web_search():
            st.write(
                  "When web search is enabled, your queries may be sent to external search services. "
                  "Results may include unverified information from the internet. "
                  "It is your responsibility to not share any internal information and to verify the output. "
                  "Are you sure you want to proceed?"
            )
            col_yes, col_no = st.columns(2)
            with col_yes:
                  if st.button("Yes, enable", use_container_width=True):
                        st.session_state["web_search_enabled"] = True
                        st.rerun()
            with col_no:
                  if st.button("Cancel", use_container_width=True):
                        st.session_state["web_search_enabled"] = False
                        st.session_state["web_search_toggle_value"] = False
                        st.session_state["web_search_cancelled"] = True
                        st.rerun()
      confirm_web_search()
elif not web_search_toggle and not has_messages:
      st.session_state["web_search_enabled"] = False
      st.session_state.pop("web_search_cancelled", None)

web_search_enabled = st.session_state.get("web_search_enabled", False)

# Select agent based on toggle
if web_search_enabled:
      active_agent_id = AGENT_SEARCH_ID
      active_alias_id = AGENT_SEARCH_ALIAS_ID
else:
      active_agent_id = AGENT_ID
      active_alias_id = AGENT_ALIAS_ID

keep_session = st.sidebar.toggle("Session history", value=True, key="keep_session")

if not keep_session:
      st.session_state["session_id"] = str(uuid.uuid4())

if st.sidebar.button("Clear chat", icon="✏️"):
      st.session_state["messages"] = []
      st.session_state["web_search_enabled"] = False
      st.session_state["s3_refs"] = []
      st.session_state["web_refs"] = []
      # Clear saved feedback markers
      keys_to_remove = [k for k in st.session_state if k.startswith("feedback_")]
      for k in keys_to_remove:
            del st.session_state[k]
      st.rerun()
      
prompt = st.chat_input(
      "Type your question here..."
)

if prompt:
      if prompt.strip() == "": 
            st.chat_message("assistant").markdown("Please enter your question before submitting.")
            
      else:
            st.chat_message("user").markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})

            with st.spinner('Your question is being processed'):
                  # Reset sources for new question
                  st.session_state["s3_refs"] = []
                  st.session_state["web_refs"] = []

                  response = query_agent(prompt, st.session_state["session_id"], active_agent_id, active_alias_id)
                  for event in response.get("completion"):
                        
                        #Collect agent output.
                        if 'chunk' in event:
                              chunk = event["chunk"]
                              if chunk.get('attribution'):
                                    for c in chunk['attribution']['citations']:
                                          for ref in c["retrievedReferences"]:
                                                if ref["location"]["type"] == "S3":
                                                      st.session_state["s3_refs"].append(ref["location"]["s3Location"]["uri"])
                                                elif ref["location"]["type"] == "WEB":
                                                      st.session_state["web_refs"].append(ref["location"]["webLocation"]["url"])

                              reply = chunk['bytes'].decode()

                              with st.chat_message("assistant"):
                                    st.markdown(reply)
                                    st.session_state.messages.append({"role": "assistant", "content": reply})
                              
                        
                        # Log trace output.
                        if 'trace' in event:
                              trace_event = event.get("trace")
                              trace = trace_event['trace']
                              for key, value in trace.items():
                                    logging.info("%s: %s",key,value)

            st.rerun()

st.sidebar.write("**Sources** :bulb:")
s3_refs_collected = st.session_state.get("s3_refs", [])
web_refs = st.session_state.get("web_refs", [])

if s3_refs_collected or web_refs:
      # Deduplicate
      s3_refs_collected = list(set(s3_refs_collected))
      web_refs = list(set(web_refs))

      # Display web refs that came directly as WEB type
      for web in web_refs:
            st.sidebar.markdown(f"🌐 [{web}]({web})")

      # Process S3 references
      shown_pdfs = set()
      shown_urls = set()

      for uri in s3_refs_collected:
            bucket, key, filename = parse_s3_uri(uri)

            # Website content .txt → show original URL from metadata
            if bucket == BUCKET_WEBSITE:
                  try:
                        metadata = s3_head_object(bucket, key)
                        source_url = metadata.get("source_url", "")
                        if source_url and source_url not in shown_urls:
                              shown_urls.add(source_url)
                              st.sidebar.markdown(f"🌐 [{source_url}]({source_url})")
                        elif not source_url:
                              st.sidebar.write(f"🌐 {filename} (source URL not available)")
                  except Exception:
                        st.sidebar.write(f"🌐 {filename}")

            # Extracted text .txt → download corresponding PDF
            elif bucket == BUCKET_EXTRACTED_TEXT:
                  try:
                        # Strip _partN suffix and replace .txt with .pdf
                        pdf_filename = re.sub(r"_part\d+\.txt$", ".pdf", filename)
                        if pdf_filename == filename:
                              # No _partN suffix, just replace .txt
                              pdf_filename = filename.replace(".txt", ".pdf")

                        if pdf_filename in shown_pdfs:
                              continue
                        shown_pdfs.add(pdf_filename)

                        pdf_key = pdf_filename
                        st.sidebar.download_button(
                              label=pdf_filename,
                              file_name=pdf_filename,
                              key=f"{pdf_filename}",
                              data=s3_get_object(BUCKET_PDF, pdf_key),
                              on_click='ignore',
                              icon="📃",
                              mime="application/pdf"
                        )
                  except Exception as e:
                        st.sidebar.write(f"📃 {filename} (PDF not available)")

            # Any other S3 bucket — fallback: offer download as-is
            else:
                  try:
                        st.sidebar.download_button(
                              label=filename,
                              file_name=filename,
                              key=f"{uri}",
                              data=s3_get_object(bucket, key),
                              on_click='ignore',
                              icon="📃",
                              mime="application/octet-stream"
                        )
                  except Exception:
                        st.sidebar.write(f"📃 {filename}")

