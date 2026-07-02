import streamlit as st
import logging
import re
import uuid
import base64
import json
import os
from src.utils import parse_s3_uri, query_agent, s3_get_object, s3_head_object, save_feedback, AGENT_ID, AGENT_ALIAS_ID, AGENT_SEARCH_ID, AGENT_SEARCH_ALIAS_ID, PDF_BUCKET, EXTRACTED_BUCKET, WEBSITE_BUCKET, FEDLEX_BUCKET
from src.document_processing import extract_text, prepare_document_context, find_relevant_chunks
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


def render_response_with_downloads(response_text):
    """Render the agent response, replacing presigned S3 URLs with styled
    download buttons. The browser downloads directly from S3 — no ECS
    memory used."""
    # Match presigned S3 URLs (contain X-Amz-Algorithm signature params)
    pattern = r'(https://[^\s]+X-Amz-Algorithm[^\s]+)'
    urls = re.findall(pattern, response_text)

    if not urls:
        st.markdown(response_text)
        return

    # Remove raw URLs from text
    clean_text = response_text
    for url in urls:
        clean_text = clean_text.replace(url, "")

    # Render the text
    st.markdown(clean_text.strip())

    # Render each URL as a styled download button
    for url in urls:
        st.markdown(
            f'<a href="{url}" target="_blank" style="display:inline-block;'
            f'padding:8px 16px;background-color:#003366;color:white;'
            f'border-radius:4px;text-decoration:none;margin-top:8px;">'
            f'📄 PDF herunterladen</a>',
            unsafe_allow_html=True,
        )


# Initialize sources in session state (only last answer's sources are kept)
if "s3_refs" not in st.session_state:
      st.session_state["s3_refs"] = []
if "web_refs" not in st.session_state:
      st.session_state["web_refs"] = []

# Bucket names (loaded from environment in src/utils.py)
BUCKET_EXTRACTED_TEXT = EXTRACTED_BUCKET
BUCKET_PDF = PDF_BUCKET
BUCKET_WEBSITE = WEBSITE_BUCKET
BUCKET_FEDLEX = FEDLEX_BUCKET

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
    You can upload a document (PDF, TXT, DOCX, XLSX, CSV) via the sidebar to ask questions about it during your session.
    You can rate answers with thumbs up/down and leave a short text comment via the 💬 button.
    For any questions or requests you can [contact us](mailto:digitalisierung@bfe.admin.ch) at the Digital Innovation & Geoinformation section :blush:
    """)

for idx, message in enumerate(st.session_state.messages):
      with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                  render_response_with_downloads(message["content"])
            else:
                  st.markdown(message["content"])
            if message["role"] == "assistant":
                  # Show collapsible reasoning steps if available
                  trace_steps = message.get("trace_steps", [])
                  if trace_steps:
                        with st.expander("🔎 Show reasoning", expanded=False):
                              for step in trace_steps:
                                    st.markdown(f"**{step['label']}**")
                                    if step.get("detail"):
                                          st.code(step["detail"], language=None)
                                    st.markdown("---")

                  feedback_key = f"feedback_{idx}"
                  comment_key = f"comment_{idx}"

                  # Layout: thumbs + comment button on one row
                  fb_col, comment_btn_col = st.columns([3, 1])
                  with fb_col:
                        score = st.feedback("thumbs", key=feedback_key)
                  with comment_btn_col:
                        # Show ✅ if comment already saved, otherwise show 💬 toggle
                        if st.session_state.get(f"{comment_key}_saved"):
                              st.markdown("✅ Comment saved")
                        else:
                              if st.button("💬", key=f"{comment_key}_btn", help="Add a text comment about this answer"):
                                    st.session_state[f"{comment_key}_open"] = not st.session_state.get(f"{comment_key}_open", False)

                  # Handle thumbs feedback save
                  if score is not None and st.session_state.get(f"{feedback_key}_saved") != score:
                        # Find the preceding user message
                        user_query = ""
                        for prev in range(idx - 1, -1, -1):
                              if st.session_state.messages[prev]["role"] == "user":
                                    user_query = st.session_state.messages[prev]["content"]
                                    break
                        rating = "positive" if score == 1 else "negative"
                        agent_variant = "web_search" if st.session_state.get("web_search_enabled", False) else "default"
                        retrieved_chunks = message.get("retrieved_chunks", [])
                        save_feedback(
                              session_id=st.session_state["session_id"],
                              message_index=idx,
                              rating=rating,
                              user_query=user_query,
                              agent_response=message["content"],
                              agent_variant=agent_variant,
                              retrieved_chunks=retrieved_chunks,
                              s3_key_override=message.get("feedback_s3_key"),
                              original_timestamp=message.get("feedback_timestamp"),
                              comment=message.get("feedback_comment"),
                        )
                        st.session_state[f"{feedback_key}_saved"] = score

                  # Show text comment area when toggled open
                  if st.session_state.get(f"{comment_key}_open"):
                        comment_text = st.text_area(
                              "What worked or didn't work?",
                              key=f"{comment_key}_text",
                              placeholder="e.g. The answer was mostly correct but missed...",
                              max_chars=1000,
                        )
                        if st.button("Send feedback", key=f"{comment_key}_send", type="primary"):
                              if comment_text and comment_text.strip():
                                    # Find the preceding user message
                                    user_query = ""
                                    for prev in range(idx - 1, -1, -1):
                                          if st.session_state.messages[prev]["role"] == "user":
                                                user_query = st.session_state.messages[prev]["content"]
                                                break
                                    # Use existing rating if available
                                    saved_score = st.session_state.get(f"{feedback_key}_saved")
                                    if saved_score is not None:
                                          rating = "positive" if saved_score == 1 else "negative"
                                    else:
                                          rating = None
                                    agent_variant = "web_search" if st.session_state.get("web_search_enabled", False) else "default"
                                    retrieved_chunks = message.get("retrieved_chunks", [])
                                    save_feedback(
                                          session_id=st.session_state["session_id"],
                                          message_index=idx,
                                          rating=rating,
                                          user_query=user_query,
                                          agent_response=message["content"],
                                          agent_variant=agent_variant,
                                          retrieved_chunks=retrieved_chunks,
                                          s3_key_override=message.get("feedback_s3_key"),
                                          original_timestamp=message.get("feedback_timestamp"),
                                          comment=comment_text.strip(),
                                    )
                                    # Store comment in message for persistence across reruns
                                    st.session_state.messages[idx]["feedback_comment"] = comment_text.strip()
                                    st.session_state[f"{comment_key}_saved"] = True
                                    st.session_state[f"{comment_key}_open"] = False
                                    st.rerun()

st.sidebar.write("**Settings**  :pushpin:")

# Detect interrupted query — show warning and retry button
pending_query = st.session_state.get("pending_query")
if pending_query:
      # Check if the last message is still the user's question (no assistant reply followed)
      messages = st.session_state.get("messages", [])
      if messages and messages[-1]["role"] == "user":
            st.warning("⚠️ The response was interrupted (e.g. by a button click). Your question was not answered.")
            if st.button("🔄 Retry last question", type="primary"):
                  # Remove the pending user message so it gets re-added cleanly
                  st.session_state.messages.pop()
                  st.session_state.pop("pending_query", None)
                  # Re-inject the prompt via session state trick
                  st.session_state["retry_prompt"] = pending_query
                  st.rerun()
      else:
            # The reply was actually saved — clean up stale flag
            st.session_state.pop("pending_query", None)

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
                        # Clear document upload state — not compatible with web search
                        st.session_state.pop("doc_full_text", None)
                        st.session_state.pop("doc_context", None)
                        st.session_state.pop("doc_context_mode", None)
                        st.session_state.pop("uploaded_doc_name", None)
                        st.session_state.pop("uploaded_doc_pages", None)
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

# ---------------------------------------------------------------------------
# Document Upload
# ---------------------------------------------------------------------------
st.sidebar.divider()
st.sidebar.write("**Document Upload** :page_facing_up:")

if web_search_enabled:
      st.sidebar.info("Document upload is not available when web search is enabled.")
      uploaded_file = None
else:
      uploaded_file = st.sidebar.file_uploader(
            "Upload a document to ask questions about it",
            type=["pdf", "txt", "docx", "xlsx", "csv"],
            key="doc_uploader",
            help="Supported formats: PDF, TXT, DOCX, XLSX, CSV (max 20 MB)",
      )

# Process newly uploaded file
if uploaded_file is not None:
      # Check if this is a new file (different from what's already processed)
      current_doc_name = st.session_state.get("uploaded_doc_name")
      if current_doc_name != uploaded_file.name:
            with st.sidebar:
                  with st.spinner("Extracting text…"):
                        try:
                              file_bytes = uploaded_file.read()
                              extracted_text, page_count = extract_text(file_bytes, uploaded_file.name)

                              # Store full text for targeted retrieval
                              st.session_state["doc_full_text"] = extracted_text

                              # Determine context strategy
                              doc_context, context_mode = prepare_document_context(
                                    extracted_text,
                                    file_ext=uploaded_file.name.rsplit(".", 1)[-1].lower(),
                              )
                              st.session_state["doc_context"] = doc_context
                              st.session_state["doc_context_mode"] = context_mode
                              st.session_state["uploaded_doc_name"] = uploaded_file.name
                              st.session_state["uploaded_doc_pages"] = page_count

                        except ValueError as e:
                              st.error(str(e))
                              st.session_state.pop("doc_full_text", None)
                              st.session_state.pop("doc_context", None)
                              st.session_state.pop("doc_context_mode", None)
                              st.session_state.pop("uploaded_doc_name", None)
                              st.session_state.pop("uploaded_doc_pages", None)
                        except Exception as e:
                              logging.error("Document extraction failed: %s", e)
                              st.error("Failed to extract text from the document. Please try another file.")
                              st.session_state.pop("doc_full_text", None)
                              st.session_state.pop("doc_context", None)
                              st.session_state.pop("doc_context_mode", None)
                              st.session_state.pop("uploaded_doc_name", None)
                              st.session_state.pop("uploaded_doc_pages", None)

# Show document status and remove button
if st.session_state.get("uploaded_doc_name") and not web_search_enabled:
      doc_name = st.session_state["uploaded_doc_name"]
      page_count = st.session_state.get("uploaded_doc_pages", "?")
      context_mode = st.session_state.get("doc_context_mode", "full")
      mode_label = "full text" if context_mode == "full" else ("chunk retrieval" if context_mode == "chunks_only" else "summary")

      st.sidebar.success(f"📄 **{doc_name}** ({page_count} pages, {mode_label})")

      if context_mode == "summary":
            st.sidebar.caption(
                  "ℹ️ Document is large — working from a summary. "
                  "Ask about specific sections for detailed answers."
            )
      elif context_mode == "chunks_only":
            st.sidebar.caption(
                  "ℹ️ Large table — relevant rows will be retrieved for each question."
            )

      if st.sidebar.button("Remove document", icon="🗑️", key="remove_doc"):
            st.session_state.pop("doc_full_text", None)
            st.session_state.pop("doc_context", None)
            st.session_state.pop("doc_context_mode", None)
            st.session_state.pop("uploaded_doc_name", None)
            st.session_state.pop("uploaded_doc_pages", None)
            st.rerun()

st.sidebar.divider()

keep_session = st.sidebar.toggle("Session history", value=True, key="keep_session")

if not keep_session:
      st.session_state["session_id"] = str(uuid.uuid4())

if st.sidebar.button("Clear chat", icon="✏️"):
      st.session_state["messages"] = []
      st.session_state["web_search_enabled"] = False
      st.session_state["s3_refs"] = []
      st.session_state["web_refs"] = []
      # Clear document upload state
      st.session_state.pop("doc_full_text", None)
      st.session_state.pop("doc_context", None)
      st.session_state.pop("doc_context_mode", None)
      st.session_state.pop("uploaded_doc_name", None)
      st.session_state.pop("uploaded_doc_pages", None)
      # Clear pending/retry state
      st.session_state.pop("pending_query", None)
      st.session_state.pop("retry_prompt", None)
      # Clear saved feedback markers
      keys_to_remove = [k for k in st.session_state if k.startswith("feedback_") or k.startswith("comment_")]
      for k in keys_to_remove:
            del st.session_state[k]
      st.rerun()
      
prompt = st.chat_input(
      "Type your question here..."
)

# Check if there's a retry prompt from an interrupted query
if not prompt and st.session_state.get("retry_prompt"):
      prompt = st.session_state.pop("retry_prompt")

if prompt:
      if prompt.strip() == "": 
            st.chat_message("assistant").markdown("Please enter your question before submitting.")
            
      else:
            st.chat_message("user").markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})

            # Mark that we're about to process — used to detect interruptions
            st.session_state["pending_query"] = prompt

            # Reset sources for new question
            st.session_state["s3_refs"] = []
            st.session_state["web_refs"] = []
            st.session_state["retrieved_chunks"] = []

            # Build session attributes for document context
            session_attributes = None
            if st.session_state.get("doc_context") and not web_search_enabled:
                  doc_context = st.session_state["doc_context"]
                  context_mode = st.session_state.get("doc_context_mode", "full")

                  # For summary or chunks_only mode, try targeted chunk retrieval for relevant details
                  if context_mode in ("summary", "chunks_only") and st.session_state.get("doc_full_text"):
                        is_tabular = context_mode == "chunks_only"
                        relevant_chunks = find_relevant_chunks(
                              st.session_state["doc_full_text"], prompt, is_tabular=is_tabular
                        )
                        if relevant_chunks:
                              if context_mode == "chunks_only":
                                    doc_context = f"RELEVANT DATA:\n{relevant_chunks}"
                              else:
                                    doc_context = (
                                          f"DOCUMENT SUMMARY:\n{doc_context}\n\n"
                                          f"RELEVANT SECTIONS:\n{relevant_chunks}"
                                    )

                  session_attributes = {
                        "uploaded_document": doc_context,
                        "document_name": st.session_state.get("uploaded_doc_name", ""),
                        "context_mode": context_mode,
                  }

            response = query_agent(
                  prompt,
                  st.session_state["session_id"],
                  active_agent_id,
                  active_alias_id,
                  session_attributes=session_attributes,
            )

            # Show live progress, then transition to reasoning expander
            with st.status("Processing your question...", expanded=False) as status:
                  trace_steps = []        # Steps with details for the expander
                  shown_labels = set()    # Dedup for live status display
                  reply = None

                  for event in response.get("completion"):

                        # Collect agent output.
                        if 'chunk' in event:
                              chunk = event["chunk"]
                              if chunk.get('attribution'):
                                    for c in chunk['attribution']['citations']:
                                          for ref in c["retrievedReferences"]:
                                                chunk_text = ref.get("content", {}).get("text", "")
                                                if ref["location"]["type"] == "S3":
                                                      source = ref["location"]["s3Location"]["uri"]
                                                      st.session_state["s3_refs"].append(source)
                                                elif ref["location"]["type"] == "WEB":
                                                      source = ref["location"]["webLocation"]["url"]
                                                      st.session_state["web_refs"].append(source)
                                                else:
                                                      source = ""
                                                if chunk_text:
                                                      st.session_state["retrieved_chunks"].append({
                                                            "text": chunk_text,
                                                            "source": source,
                                                      })

                              reply = chunk['bytes'].decode()

                        # Parse trace events for user-friendly status updates
                        if 'trace' in event:
                              trace_event = event.get("trace")
                              trace = trace_event['trace']
                              for key, value in trace.items():
                                    logging.info("%s: %s", key, value)

                                    # Map trace keys to human-readable labels with details
                                    if key == "preProcessingTrace":
                                          live_label = "🧠 Analyzing your question..."
                                          if live_label not in shown_labels:
                                                shown_labels.add(live_label)
                                                status.update(label=live_label)

                                    elif key == "orchestrationTrace":
                                          if isinstance(value, dict):
                                                if "rationale" in value:
                                                      step_label = "💭 Reasoning"
                                                      detail = value["rationale"].get("text", "")
                                                      if detail:
                                                            trace_steps.append({"label": step_label, "detail": detail})
                                                      live_label = "💭 Reasoning..."
                                                      if live_label not in shown_labels:
                                                            shown_labels.add(live_label)
                                                            status.update(label=live_label)

                                                elif "invocationInput" in value:
                                                      inv = value["invocationInput"]
                                                      if "knowledgeBaseLookupInput" in inv:
                                                            kb_input = inv["knowledgeBaseLookupInput"]
                                                            kb_id = kb_input.get("knowledgeBaseId", "")
                                                            query_text = kb_input.get("text", "")
                                                            step_label = "📚 Knowledge base query"
                                                            detail = f"Knowledge Base: {kb_id}\nQuery: {query_text}"
                                                            trace_steps.append({"label": step_label, "detail": detail})
                                                            status.update(label="📚 Searching knowledge base...")
                                                      elif "actionGroupInvocationInput" in inv:
                                                            ag_input = inv["actionGroupInvocationInput"]
                                                            ag_name = ag_input.get("actionGroupName", "unknown")
                                                            api_path = ag_input.get("apiPath", ag_input.get("function", ""))
                                                            step_label = f"⚙️ Calling: {ag_name}"
                                                            detail = f"Action: {ag_name}\nAPI path: {api_path}" if api_path else f"Action: {ag_name}"
                                                            trace_steps.append({"label": step_label, "detail": detail})
                                                            status.update(label=f"⚙️ Calling {ag_name}...")
                                                      else:
                                                            status.update(label="🔍 Gathering information...")

                                                elif "observation" in value:
                                                      obs = value["observation"]
                                                      if "knowledgeBaseLookupOutput" in obs:
                                                            kb_output = obs["knowledgeBaseLookupOutput"]
                                                            refs = kb_output.get("retrievedReferences", [])
                                                            step_label = f"📚 Retrieved {len(refs)} result(s)"
                                                            previews = []
                                                            for i, ref in enumerate(refs[:5]):
                                                                  text = ref.get("content", {}).get("text", "")
                                                                  source = ""
                                                                  loc = ref.get("location", {})
                                                                  if loc.get("type") == "S3":
                                                                        source = loc.get("s3Location", {}).get("uri", "")
                                                                  elif loc.get("type") == "WEB":
                                                                        source = loc.get("webLocation", {}).get("url", "")
                                                                  preview = text[:150] + "..." if len(text) > 150 else text
                                                                  previews.append(f"[{i+1}] {preview}\n    Source: {source}")
                                                            detail = "\n".join(previews) if previews else None
                                                            if detail:
                                                                  trace_steps.append({"label": step_label, "detail": detail})
                                                            status.update(label=f"📚 Retrieved {len(refs)} result(s)")
                                                      elif "actionGroupInvocationOutput" in obs:
                                                            ag_output = obs["actionGroupInvocationOutput"]
                                                            output_text = ag_output.get("text", "")
                                                            step_label = "⚙️ Action result"
                                                            detail = output_text[:500] if output_text else None
                                                            if detail:
                                                                  trace_steps.append({"label": step_label, "detail": detail})
                                                            status.update(label="⚙️ Action completed")

                                                elif "modelInvocationInput" in value:
                                                      status.update(label="🤖 Thinking...")

                                    elif key == "postProcessingTrace":
                                          live_label = "✍️ Formulating response..."
                                          if live_label not in shown_labels:
                                                shown_labels.add(live_label)
                                                status.update(label=live_label)

                                    elif key == "failureTrace":
                                          reason = value.get("failureReason", "Unknown error") if isinstance(value, dict) else "Unknown error"
                                          trace_steps.append({"label": "⚠️ Error", "detail": reason})
                                          status.update(label="⚠️ An error occurred")

                  # Collapse the status widget and show reasoning details inside
                  if trace_steps:
                        for step in trace_steps:
                              st.markdown(f"**{step['label']}**")
                              if step.get("detail"):
                                    st.code(step["detail"], language=None)
                        status.update(label="🔎 Show reasoning", state="complete", expanded=False)
                  else:
                        status.update(label="✅ Done", state="complete", expanded=False)

            # Display the assistant's reply
            if reply:
                  with st.chat_message("assistant"):
                        render_response_with_downloads(reply)
                        st.session_state.messages.append({
                              "role": "assistant",
                              "content": reply,
                              "retrieved_chunks": st.session_state.get("retrieved_chunks", []),
                              "trace_steps": trace_steps,
                        })

            # Save interaction to feedback bucket (without rating) immediately
            if reply:
                  msg_index = len(st.session_state.messages) - 1
                  agent_variant = "web_search" if web_search_enabled else "default"
                  feedback_key_s3, feedback_timestamp = save_feedback(
                        session_id=st.session_state["session_id"],
                        message_index=msg_index,
                        rating=None,
                        user_query=prompt,
                        agent_response=st.session_state.messages[msg_index]["content"],
                        agent_variant=agent_variant,
                        retrieved_chunks=st.session_state.get("retrieved_chunks", []),
                  )
                  # Store the S3 key and timestamp so later feedback overwrites the same file
                  st.session_state.messages[msg_index]["feedback_s3_key"] = feedback_key_s3
                  st.session_state.messages[msg_index]["feedback_timestamp"] = feedback_timestamp

            # Clear the pending query flag — processing completed successfully
            st.session_state.pop("pending_query", None)
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

            # Fedlex law .txt → read .metadata.json for title and URL
            elif bucket == BUCKET_FEDLEX:
                  try:
                        metadata_key = key + ".metadata.json"
                        metadata_bytes = s3_get_object(bucket, metadata_key)
                        metadata_json = json.loads(metadata_bytes)
                        attrs = metadata_json.get("metadataAttributes", {})
                        fedlex_url = attrs.get("fedlex_url", {}).get("value", {}).get("stringValue", "")
                        title = attrs.get("title", {}).get("value", {}).get("stringValue", "")
                        abbreviation = attrs.get("abbreviation", {}).get("value", {}).get("stringValue", "")
                        label = f"{abbreviation} – {title}" if abbreviation and title else title or filename
                        if fedlex_url and fedlex_url not in shown_urls:
                              shown_urls.add(fedlex_url)
                              st.sidebar.markdown(f"⚖️ [{label}]({fedlex_url})")
                        elif not fedlex_url:
                              st.sidebar.write(f"⚖️ {label}")
                  except Exception:
                        st.sidebar.write(f"⚖️ {filename}")

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

                        # Preserve directory structure (e.g. aramis/) from the extracted text key
                        pdf_key = re.sub(r"_part\d+\.txt$", ".pdf", key)
                        if pdf_key == key:
                              pdf_key = key.replace(".txt", ".pdf")

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

