import os
import json
from datetime import datetime, timezone
from urllib.parse import urlparse
import boto3
from dotenv import load_dotenv
import logging

 
 
logging.basicConfig(level=logging.DEBUG)
 
st_logger = logging.getLogger("streamlit")
st_logger.setLevel(logging.INFO)
 

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION")
AGENTCORE_RUNTIME_ARN = os.getenv("AGENTCORE_RUNTIME_ARN")
AGENTCORE_ENDPOINT_ARN = os.getenv("AGENTCORE_ENDPOINT_ARN")
FEEDBACK_BUCKET = os.getenv("FEEDBACK_BUCKET")
PDF_BUCKET = os.getenv("PDF_BUCKET")
EXTRACTED_BUCKET = os.getenv("EXTRACTED_BUCKET")
WEBSITE_BUCKET = os.getenv("WEBSITE_BUCKET")
FEDLEX_BUCKET = os.getenv("FEDLEX_BUCKET")

# Legacy env vars — kept for backwards compatibility during transition
AGENT_ALIAS_ID = os.getenv("AGENT_ALIAS_ID")
AGENT_ID = os.getenv("AGENT_ID")
AGENT_SEARCH_ID = os.getenv("AGENT_SEARCH_ID")
AGENT_SEARCH_ALIAS_ID = os.getenv("AGENT_SEARCH_ALIAS_ID")



s3_client = boto3.client(
    's3',
    region_name=AWS_REGION
    )

agentcore_client = boto3.client(
    'bedrock-agentcore',
    region_name=AWS_REGION
    )


def query_agent(prompt, session_id, enable_web_search=False, session_attributes=None, files=None):
    """Invoke the AgentCore Runtime agent.

    Args:
        prompt: User message text.
        session_id: Session identifier for conversation continuity.
        enable_web_search: Whether to enable the web search tool.
        session_attributes: Dict with uploaded_document, document_name, context_mode.
        files: Code Interpreter files (not yet supported in AgentCore — see migration guide).

    Returns:
        AgentCore Runtime streaming response.
    """
    payload = {
        "prompt": prompt,
        "session_id": session_id,
        "enable_web_search": enable_web_search,
        "include_trace": True,
    }

    # Document context
    if session_attributes:
        if "uploaded_document" in session_attributes:
            payload["uploaded_document"] = session_attributes["uploaded_document"]
        if "document_name" in session_attributes:
            payload["document_name"] = session_attributes["document_name"]
        if "context_mode" in session_attributes:
            payload["context_mode"] = session_attributes["context_mode"]

    # TODO: Code Interpreter file upload — Classic used sessionState.files,
    # AgentCore needs a different approach (e.g. session storage or payload).
    # For now, tabular files processed as text will work via uploaded_document.
    if files:
        logging.warning("Code Interpreter file upload not yet supported in AgentCore. Files ignored.")

    response = agentcore_client.invoke_agent_runtime(
        agentRuntimeArn=AGENTCORE_RUNTIME_ARN,
        payload=json.dumps(payload).encode("utf-8"),
    )
    return response

def parse_s3_uri(s3_uri):
    """Parse s3://bucket/key into bucket and key"""
    if not s3_uri.startswith("s3://"):
        raise ValueError("Invalid S3 URI. It should start with 's3://'")
    
    parsed = urlparse(s3_uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip('/')
    filename = os.path.basename(key)
    return bucket, key, filename

def s3_get_object(bucket, key):
    return s3_client.get_object(Bucket=bucket, Key=key)['Body'].read()

def s3_head_object(bucket, key):
    """Get S3 object metadata (user-defined metadata)."""
    response = s3_client.head_object(Bucket=bucket, Key=key)
    return response.get("Metadata", {})


def save_feedback(session_id, message_index, rating, user_query, agent_response, agent_variant, retrieved_chunks=None, s3_key_override=None, original_timestamp=None, comment=None, action_groups_used=None):
    """Save user feedback (thumbs up/down + optional text comment) to S3 as a JSON file.
    
    If s3_key_override is provided, uses that key (to overwrite a previously saved record).
    Otherwise generates a new key based on the current date.
    If original_timestamp is provided, preserves it instead of using current time.
    Returns a tuple of (s3_key, timestamp).
    """
    if not FEEDBACK_BUCKET:
        logging.warning("FEEDBACK_BUCKET not configured, skipping feedback save.")
        return None, None

    now = datetime.now(timezone.utc)
    timestamp = original_timestamp or now.isoformat()

    feedback = {
        "session_id": session_id,
        "timestamp": timestamp,
        "rating": rating,
        "user_query": user_query,
        "agent_response": agent_response,
        "agent_variant": agent_variant,
        "message_index": message_index,
        "retrieved_chunks": retrieved_chunks or [],
        "comment": comment,
        "action_groups_used": action_groups_used or [],
    }

    key = s3_key_override or f"feedback/{now.year}/{now.month:02d}/{now.day:02d}/{session_id}_{message_index}.json"

    s3_client.put_object(
        Bucket=FEEDBACK_BUCKET,
        Key=key,
        Body=json.dumps(feedback, ensure_ascii=False),
        ContentType="application/json",
    )
    return key, timestamp
