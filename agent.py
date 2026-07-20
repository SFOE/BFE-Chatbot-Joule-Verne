import streamlit as st
import logging
import re
import uuid
import base64
import json
import os
from src.utils import parse_s3_uri, query_agent, s3_get_object, s3_head_object, save_feedback, AGENT_ID, AGENT_ALIAS_ID, AGENT_SEARCH_ID, AGENT_SEARCH_ALIAS_ID, PDF_BUCKET, EXTRACTED_BUCKET, WEBSITE_BUCKET, FEDLEX_BUCKET
from src.document_processing import (
    process_multiple_documents, build_multi_doc_context, build_code_interpreter_files,
    MAX_UPLOAD_FILES,
)
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
    st.error("403 - Zugriff verweigert: Sie sind nicht berechtigt, auf diese Anwendung zuzugreifen.")
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

# Streamlit bietet keine Spracheinstellung — Widget-Texte per CSS auf Deutsch überschreiben
st.markdown("""
<style>
[data-testid='stFileUploaderDropzone'] > [data-testid='baseButton-secondary'] {
    text-indent: -9999px;
    line-height: 0;
}
[data-testid='stFileUploaderDropzone'] > [data-testid='baseButton-secondary']::after {
    content: "Durchsuchen";
    text-indent: 0;
    line-height: initial;
    display: block;
}
[data-testid='stFileUploaderDropzoneInstructions'] > div > span {
    display: none;
}
[data-testid='stFileUploaderDropzoneInstructions'] > div::before {
    content: "Dateien hierher ziehen";
    display: block;
}
[data-testid='stFileUploaderDropzoneInstructions'] > div > small {
    display: none;
}
[data-testid='stFileUploaderDropzoneInstructions'] > div::after {
    content: "PDF, TXT, DOCX, XLSX, CSV" "\\A" "Max. 10 MB pro Datei · bis zu 5 Dateien";
    white-space: pre-wrap;
    display: block;
    font-size: 0.8em;
    color: rgba(49, 51, 63, 0.6);
}
</style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([1,8])

with col1:
      st.markdown(" ") 
      st.image("./img/bundesamt_logo.jpeg", width=60)

with col2:
      st.title("BFE Assistent Joule Verne 1.0")

st.caption("🔒 Ihre Interaktionen werden protokolliert, um diesen Chatbot zu verbessern.")

with st.expander(":information_source: :construction:"):
    st.write("""
    Dies ist eine Demo-Anwendung, die noch weiterentwickelt wird. Der Chatbot ist nicht immer korrekt oder präzise. Bitte überprüfen Sie die Quellen in der Seitenleiste, wenn Sie unsicher sind. Achten Sie darauf, keine persönlichen Daten im Chat hochzuladen.
    Sie können mehrere Dokumente (PDF, TXT, DOCX, XLSX, CSV) über die Seitenleiste hochladen, um während Ihrer Sitzung Fragen dazu zu stellen.
    Sie können Antworten mit Daumen hoch/runter bewerten und über die 💬-Schaltfläche einen kurzen Textkommentar hinterlassen.
    Bei Fragen oder Anliegen können Sie uns bei der Sektion Digitalisierung & Informatik [kontaktieren](mailto:digitalisierung@bfe.admin.ch) :blush:
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
                        display_prefixes = ("💭", "⚙️", "🖥️", "⚠️")
                        filtered_steps = [s for s in trace_steps if s["label"].startswith(display_prefixes)]
                        if filtered_steps:
                              with st.expander("🔎 Denkprozess anzeigen", expanded=False):
                                    for step in filtered_steps:
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
                              st.markdown("✅ Kommentar gespeichert")
                        else:
                              if st.button("💬", key=f"{comment_key}_btn", help="Einen Textkommentar zu dieser Antwort hinzufügen"):
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
                              action_groups_used=message.get("action_groups_used", []),
                        )
                        st.session_state[f"{feedback_key}_saved"] = score

                  # Show text comment area when toggled open
                  if st.session_state.get(f"{comment_key}_open"):
                        comment_text = st.text_area(
                              "Was hat funktioniert oder nicht funktioniert?",
                              key=f"{comment_key}_text",
                              placeholder="z.B. Die Antwort war grösstenteils korrekt, aber es fehlte...",
                              max_chars=1000,
                        )
                        if st.button("Feedback senden", key=f"{comment_key}_send", type="primary"):
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
                                          action_groups_used=message.get("action_groups_used", []),
                                    )
                                    # Store comment in message for persistence across reruns
                                    st.session_state.messages[idx]["feedback_comment"] = comment_text.strip()
                                    st.session_state[f"{comment_key}_saved"] = True
                                    st.session_state[f"{comment_key}_open"] = False
                                    st.rerun()

st.sidebar.write("**Einstellungen**  :pushpin:")

# Detect interrupted query — show warning and retry button
pending_query = st.session_state.get("pending_query")
if pending_query:
      # Check if the last message is still the user's question (no assistant reply followed)
      messages = st.session_state.get("messages", [])
      if messages and messages[-1]["role"] == "user":
            st.warning("⚠️ Die Antwort wurde unterbrochen (z.B. durch einen Klick). Ihre Frage wurde nicht beantwortet.")
            if st.button("🔄 Letzte Frage erneut stellen", type="primary"):
                  # Remove the pending user message so it gets re-added cleanly
                  st.session_state.messages.pop()
                  st.session_state.pop("pending_query", None)
                  # Re-inject the prompt via session state trick
                  st.session_state["retry_prompt"] = pending_query
                  st.rerun()
      else:
            # The reply was actually saved — clean up stale flag
            st.session_state.pop("pending_query", None)

# Suchmodus-Auswahl — gesperrt sobald die Konversation gestartet ist
has_messages = len(st.session_state.get("messages", [])) > 0

# Initialize search mode
if "search_mode" not in st.session_state:
      st.session_state["search_mode"] = "knowledge_base"

# Key changes when user cancels web search, forcing the radio widget to reset
search_radio_key = f"search_mode_radio_{st.session_state.get('search_radio_key', 0)}"

search_mode = st.sidebar.radio(
      "🔍 Suchmodus",
      options=["knowledge_base", "web_search"],
      format_func=lambda x: "📚 BFE-Wissen" if x == "knowledge_base" else "🌐 Websuche",
      index=0 if st.session_state.get("search_mode") == "knowledge_base" else 1,
      disabled=has_messages,
      help="Wählen Sie zwischen internem BFE-Wissen und externer Websuche. Kann nur vor der ersten Nachricht geändert werden.",
      key=search_radio_key,
)

# Confirmation dialog when user selects web search
if search_mode == "web_search" and not st.session_state.get("web_search_enabled", False) and not st.session_state.pop("web_search_cancelled", False):
      @st.dialog("⚠️ Websuche aktivieren?")
      def confirm_web_search():
            st.write(
                  "Wenn die Websuche aktiviert ist, können Ihre Anfragen an externe Suchdienste gesendet werden. "
                  "Ergebnisse können ungeprüfte Informationen aus dem Internet enthalten. "
                  "Es liegt in Ihrer Verantwortung, keine internen Informationen zu teilen und die Ergebnisse zu überprüfen. "
                  "Möchten Sie fortfahren?"
            )
            col_yes, col_no = st.columns(2)
            with col_yes:
                  if st.button("Ja, aktivieren", use_container_width=True):
                        st.session_state["web_search_enabled"] = True
                        st.session_state["search_mode"] = "web_search"
                        # Clear document upload state — not compatible with web search
                        st.session_state.pop("uploaded_docs_text", None)
                        st.session_state.pop("uploaded_docs_ci", None)
                        st.session_state.pop("uploaded_doc_names", None)
                        st.session_state.pop("uploaded_doc_fingerprints", None)
                        st.session_state.pop("uploaded_doc_errors", None)
                        st.session_state["doc_uploader_key"] = st.session_state.get("doc_uploader_key", 0) + 1
                        st.rerun()
            with col_no:
                  if st.button("Abbrechen", use_container_width=True):
                        st.session_state["web_search_enabled"] = False
                        st.session_state["search_mode"] = "knowledge_base"
                        st.session_state["web_search_cancelled"] = True
                        # Increment radio key to force widget reset to knowledge_base
                        st.session_state["search_radio_key"] = st.session_state.get("search_radio_key", 0) + 1
                        st.rerun()
      confirm_web_search()
elif search_mode == "knowledge_base" and not has_messages:
      st.session_state["web_search_enabled"] = False
      st.session_state["search_mode"] = "knowledge_base"
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
st.sidebar.write("**Dokumente hochladen** :page_facing_up:")

if web_search_enabled:
      st.sidebar.info("Dokument-Upload ist nicht verfügbar, wenn die Websuche aktiviert ist.")
      uploaded_files = None
else:
      uploaded_files = st.sidebar.file_uploader(
            "Laden Sie Dokumente hoch, um Fragen dazu zu stellen",
            type=["pdf", "txt", "docx", "xlsx", "csv"],
            accept_multiple_files=True,
            key=f"doc_uploader_{st.session_state.get('doc_uploader_key', 0)}",
            help=f"Unterstützte Formate: PDF, TXT, DOCX, XLSX, CSV (max. 10 MB pro Datei, bis zu {MAX_UPLOAD_FILES} Dateien)",
      )

# Process newly uploaded files
if uploaded_files:
      # Check file count limit
      if len(uploaded_files) > MAX_UPLOAD_FILES:
            st.sidebar.error(f"Maximal {MAX_UPLOAD_FILES} Dateien erlaubt. Bitte entfernen Sie einige Dateien.")
      else:
            # Determine which files are new (not yet processed)
            current_doc_names = set(st.session_state.get("uploaded_doc_names", []))
            new_file_fingerprints = {f"{f.name}_{f.size}" for f in uploaded_files}
            old_fingerprints = set(st.session_state.get("uploaded_doc_fingerprints", []))

            if new_file_fingerprints != old_fingerprints:
                  with st.sidebar:
                        with st.spinner("Dokumente werden verarbeitet…"):
                              try:
                                    files_data = []
                                    for f in uploaded_files:
                                          file_bytes = f.read()
                                          files_data.append({"name": f.name, "bytes": file_bytes})

                                    processed = process_multiple_documents(files_data)

                                    # Store results in session state
                                    st.session_state["uploaded_docs_text"] = processed["text_docs"]
                                    st.session_state["uploaded_docs_ci"] = processed["code_interpreter_docs"]
                                    st.session_state["uploaded_doc_names"] = [f.name for f in uploaded_files]
                                    st.session_state["uploaded_doc_fingerprints"] = list(new_file_fingerprints)
                                    st.session_state["uploaded_doc_errors"] = processed["errors"]

                              except Exception as e:
                                    logging.error("Document processing failed: %s", e)
                                    st.error("Dokumente konnten nicht verarbeitet werden. Bitte versuchen Sie es erneut.")
                                    st.session_state.pop("uploaded_docs_text", None)
                                    st.session_state.pop("uploaded_docs_ci", None)
                                    st.session_state.pop("uploaded_doc_names", None)
                                    st.session_state.pop("uploaded_doc_fingerprints", None)
                                    st.session_state.pop("uploaded_doc_errors", None)

elif not uploaded_files and st.session_state.get("uploaded_doc_names") and not web_search_enabled:
      # User cleared all files via the widget
      st.session_state.pop("uploaded_docs_text", None)
      st.session_state.pop("uploaded_docs_ci", None)
      st.session_state.pop("uploaded_doc_names", None)
      st.session_state.pop("uploaded_doc_fingerprints", None)
      st.session_state.pop("uploaded_doc_errors", None)

# Show document status
if st.session_state.get("uploaded_doc_names") and not web_search_enabled:
      text_docs = st.session_state.get("uploaded_docs_text", [])
      ci_docs = st.session_state.get("uploaded_docs_ci", [])
      errors = st.session_state.get("uploaded_doc_errors", [])

      for doc in text_docs:
            mode_label = "Volltext" if doc["context_mode"] == "full" else "Zusammenfassung"
            st.sidebar.success(f"📄 **{doc['name']}** ({doc['page_count']} Seiten, {mode_label})")

      for doc in ci_docs:
            st.sidebar.success(f"📊 **{doc['name']}** (Code Interpreter)")

      for err in errors:
            if err.get("sensitivity_blocked"):
                  st.sidebar.warning(f"🔒 **{err['name']}**: {err['error']}")
            else:
                  st.sidebar.error(f"❌ **{err['name']}**: {err['error']}")

      if text_docs and any(d["context_mode"] == "summary" for d in text_docs):
            st.sidebar.caption(
                  "ℹ️ Grosse Dokumente werden zusammengefasst. "
                  "Fragen Sie nach bestimmten Abschnitten für detaillierte Antworten."
            )

      if ci_docs:
            st.sidebar.caption(
                  "ℹ️ Grosse Tabellen werden mit Code Interpreter analysiert."
            )

      if st.sidebar.button("Alle Dokumente entfernen", icon="🗑️", key="remove_doc"):
            st.session_state.pop("uploaded_docs_text", None)
            st.session_state.pop("uploaded_docs_ci", None)
            st.session_state.pop("uploaded_doc_names", None)
            st.session_state.pop("uploaded_doc_fingerprints", None)
            st.session_state.pop("uploaded_doc_errors", None)
            st.session_state["doc_uploader_key"] = st.session_state.get("doc_uploader_key", 0) + 1
            st.rerun()

st.sidebar.divider()

keep_session = st.sidebar.toggle("Sitzungsverlauf", value=True, key="keep_session")

if not keep_session:
      st.session_state["session_id"] = str(uuid.uuid4())

if st.sidebar.button("Chat löschen", icon="✏️"):
      st.session_state["messages"] = []
      st.session_state["web_search_enabled"] = False
      st.session_state["search_mode"] = "knowledge_base"
      st.session_state["s3_refs"] = []
      st.session_state["web_refs"] = []
      # Clear document upload state
      st.session_state.pop("uploaded_docs_text", None)
      st.session_state.pop("uploaded_docs_ci", None)
      st.session_state.pop("uploaded_doc_names", None)
      st.session_state.pop("uploaded_doc_fingerprints", None)
      st.session_state.pop("uploaded_doc_errors", None)
      st.session_state["doc_uploader_key"] = st.session_state.get("doc_uploader_key", 0) + 1
      # Clear pending/retry state
      st.session_state.pop("pending_query", None)
      st.session_state.pop("retry_prompt", None)
      # Clear saved feedback markers
      keys_to_remove = [k for k in st.session_state if k.startswith("feedback_") or k.startswith("comment_")]
      for k in keys_to_remove:
            del st.session_state[k]
      st.rerun()

prompt = st.chat_input(
      "Geben Sie hier Ihre Frage ein..."
)

# Check if there's a retry prompt from an interrupted query
if not prompt and st.session_state.get("retry_prompt"):
      prompt = st.session_state.pop("retry_prompt")

if prompt:
      if prompt.strip() == "": 
            st.chat_message("assistant").markdown("Bitte geben Sie Ihre Frage ein, bevor Sie absenden.")
            
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
            agent_files = None
            text_docs = st.session_state.get("uploaded_docs_text", [])
            ci_docs = st.session_state.get("uploaded_docs_ci", [])

            if (text_docs or ci_docs) and not web_search_enabled:
                  # Build Code Interpreter files from large tabular docs
                  if ci_docs:
                        agent_files = build_code_interpreter_files(ci_docs)

                  # Build session attributes from text-based documents
                  if text_docs:
                        doc_context = build_multi_doc_context(text_docs, query=prompt)
                        doc_names = ", ".join(d["name"] for d in text_docs)
                        if ci_docs:
                              doc_names += ", " + ", ".join(d["name"] for d in ci_docs)
                        session_attributes = {
                              "uploaded_document": doc_context,
                              "document_name": doc_names,
                              "context_mode": "multi" if len(text_docs) > 1 else text_docs[0]["context_mode"],
                        }
                  elif ci_docs:
                        # Only Code Interpreter docs, no text docs — still pass document names
                        session_attributes = {
                              "uploaded_document": "[Documents sent to Code Interpreter for analysis]",
                              "document_name": ", ".join(d["name"] for d in ci_docs),
                              "context_mode": "code_interpreter",
                        }

            response = query_agent(
                  prompt,
                  st.session_state["session_id"],
                  active_agent_id,
                  active_alias_id,
                  session_attributes=session_attributes,
                  files=agent_files,
            )

            # Show live progress, then transition to reasoning expander
            with st.status("Ihre Frage wird verarbeitet...", expanded=False) as status:
                  trace_steps = []        # Steps with details for the expander
                  shown_labels = set()    # Dedup for live status display
                  action_groups_used = []  # Track which action groups were invoked
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
                                          live_label = "🧠 Ihre Frage wird analysiert..."
                                          if live_label not in shown_labels:
                                                shown_labels.add(live_label)
                                                status.update(label=live_label)

                                    elif key == "orchestrationTrace":
                                          if isinstance(value, dict):
                                                if "rationale" in value:
                                                      step_label = "💭 Überlegung"
                                                      detail = value["rationale"].get("text", "")
                                                      if detail:
                                                            trace_steps.append({"label": step_label, "detail": detail})
                                                      live_label = "💭 Überlege..."
                                                      if live_label not in shown_labels:
                                                            shown_labels.add(live_label)
                                                            status.update(label=live_label)

                                                elif "invocationInput" in value:
                                                      inv = value["invocationInput"]
                                                      if "knowledgeBaseLookupInput" in inv:
                                                            kb_input = inv["knowledgeBaseLookupInput"]
                                                            kb_id = kb_input.get("knowledgeBaseId", "")
                                                            query_text = kb_input.get("text", "")
                                                            step_label = "📚 Wissensdatenbank-Abfrage"
                                                            detail = f"Wissensdatenbank: {kb_id}\nAbfrage: {query_text}"
                                                            trace_steps.append({"label": step_label, "detail": detail})
                                                            status.update(label="📚 Wissensdatenbank wird durchsucht...")
                                                      elif "actionGroupInvocationInput" in inv:
                                                            ag_input = inv["actionGroupInvocationInput"]
                                                            ag_name = ag_input.get("actionGroupName", "unbekannt")
                                                            api_path = ag_input.get("apiPath", ag_input.get("function", ""))
                                                            step_label = f"⚙️ Aufruf: {ag_name}"
                                                            detail = f"Aktion: {ag_name}\nAPI-Pfad: {api_path}" if api_path else f"Aktion: {ag_name}"
                                                            trace_steps.append({"label": step_label, "detail": detail})
                                                            status.update(label=f"⚙️ {ag_name} wird aufgerufen...")
                                                            # Track action group usage for feedback
                                                            action_groups_used.append(ag_name)
                                                      else:
                                                            status.update(label="🔍 Informationen werden gesammelt...")

                                                elif "observation" in value:
                                                      obs = value["observation"]
                                                      if "knowledgeBaseLookupOutput" in obs:
                                                            kb_output = obs["knowledgeBaseLookupOutput"]
                                                            refs = kb_output.get("retrievedReferences", [])
                                                            step_label = f"📚 {len(refs)} Ergebnis(se) gefunden"
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
                                                                  previews.append(f"[{i+1}] {preview}\n    Quelle: {source}")
                                                            detail = "\n".join(previews) if previews else None
                                                            if detail:
                                                                  trace_steps.append({"label": step_label, "detail": detail})
                                                            status.update(label=f"📚 {len(refs)} Ergebnis(se) gefunden")
                                                      elif "actionGroupInvocationOutput" in obs:
                                                            ag_output = obs["actionGroupInvocationOutput"]
                                                            output_text = ag_output.get("text", "")
                                                            step_label = "⚙️ Aktionsergebnis"
                                                            detail = output_text[:500] if output_text else None
                                                            if detail:
                                                                  trace_steps.append({"label": step_label, "detail": detail})
                                                            status.update(label="⚙️ Aktion abgeschlossen")
                                                      elif "codeInterpreterInvocationOutput" in obs:
                                                            ci_output = obs["codeInterpreterInvocationOutput"]
                                                            # Log execution output/errors for trace
                                                            exec_output = ci_output.get("executionOutput", "")
                                                            exec_error = ci_output.get("executionError", "")
                                                            ci_file_names = ci_output.get("files", [])
                                                            if exec_error:
                                                                  trace_steps.append({"label": "🖥️ Code Interpreter Fehler", "detail": exec_error[:500]})
                                                            elif exec_output:
                                                                  trace_steps.append({"label": "🖥️ Code Interpreter", "detail": exec_output[:500]})
                                                            if ci_file_names:
                                                                  status.update(label=f"🖥️ {len(ci_file_names)} Datei(en) generiert")
                                                            else:
                                                                  status.update(label="🖥️ Code ausgeführt")

                                                elif "modelInvocationInput" in value:
                                                      status.update(label="🤖 Denke nach...")

                                    elif key == "postProcessingTrace":
                                          live_label = "✍️ Antwort wird formuliert..."
                                          if live_label not in shown_labels:
                                                shown_labels.add(live_label)
                                                status.update(label=live_label)

                                    elif key == "failureTrace":
                                          reason = value.get("failureReason", "Unbekannter Fehler") if isinstance(value, dict) else "Unbekannter Fehler"
                                          trace_steps.append({"label": "⚠️ Fehler", "detail": reason})
                                          status.update(label="⚠️ Ein Fehler ist aufgetreten")

                  # Collapse the status widget and show reasoning details inside
                  # Filter: nur wesentliche Schritte im Expander anzeigen
                  display_prefixes = ("💭", "⚙️", "🖥️", "⚠️")
                  filtered_steps = [s for s in trace_steps if s["label"].startswith(display_prefixes)]
                  if filtered_steps:
                        for step in filtered_steps:
                              st.markdown(f"**{step['label']}**")
                              if step.get("detail"):
                                    st.code(step["detail"], language=None)
                        status.update(label="🔎 Denkprozess anzeigen", state="complete", expanded=False)
                  else:
                        status.update(label="✅ Fertig", state="complete", expanded=False)

            # Display the assistant's reply
            if reply:
                  with st.chat_message("assistant"):
                        render_response_with_downloads(reply)
                        st.session_state.messages.append({
                              "role": "assistant",
                              "content": reply,
                              "retrieved_chunks": st.session_state.get("retrieved_chunks", []),
                              "trace_steps": trace_steps,
                              "action_groups_used": action_groups_used,
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
                        action_groups_used=action_groups_used,
                  )
                  # Store the S3 key and timestamp so later feedback overwrites the same file
                  st.session_state.messages[msg_index]["feedback_s3_key"] = feedback_key_s3
                  st.session_state.messages[msg_index]["feedback_timestamp"] = feedback_timestamp

            # Clear the pending query flag — processing completed successfully
            st.session_state.pop("pending_query", None)
            st.rerun()

st.sidebar.write("**Quellen** :bulb:")
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
                              st.sidebar.write(f"🌐 {filename} (Quell-URL nicht verfügbar)")
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
                        st.sidebar.write(f"📃 {filename} (PDF nicht verfügbar)")

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

# ---------------------------------------------------------------------------
# Footer (bottom of sidebar, after Quellen)
# ---------------------------------------------------------------------------
st.sidebar.divider()
st.sidebar.markdown(
      "<p style='font-size:0.8em;color:gray;'>"
      "<a href='/release_notes' target='_self'>📋 Release Notes</a>"
      "</p>",
      unsafe_allow_html=True,
)
