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
AGENT_ALIAS_ID = os.getenv("AGENT_ALIAS_ID")
AGENT_ID = os.getenv("AGENT_ID")
AGENT_SEARCH_ID = os.getenv("AGENT_SEARCH_ID")
AGENT_SEARCH_ALIAS_ID = os.getenv("AGENT_SEARCH_ALIAS_ID")
FEEDBACK_BUCKET = os.getenv("FEEDBACK_BUCKET")


s3_client = boto3.client(
    's3',
    region_name=AWS_REGION
    )

bedrock_client = boto3.client(
    'bedrock-agent-runtime',
    region_name=AWS_REGION
    )

def query_agent(prompt, session_id, agent_id=None, agent_alias_id=None):
      response = bedrock_client.invoke_agent(
            agentAliasId=agent_alias_id or AGENT_ALIAS_ID,
            agentId=agent_id or AGENT_ID,
            enableTrace=True,
            sessionId=session_id,
            inputText=prompt
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


def save_feedback(session_id, message_index, rating, user_query, agent_response, agent_variant):
    """Save user feedback (thumbs up/down) to S3 as a JSON file."""
    if not FEEDBACK_BUCKET:
        logging.warning("FEEDBACK_BUCKET not configured, skipping feedback save.")
        return

    now = datetime.now(timezone.utc)
    feedback = {
        "session_id": session_id,
        "timestamp": now.isoformat(),
        "rating": rating,
        "user_query": user_query,
        "agent_response": agent_response,
        "agent_variant": agent_variant,
        "message_index": message_index,
    }

    key = f"feedback/{now.year}/{now.month:02d}/{now.day:02d}/{session_id}_{message_index}.json"

    s3_client.put_object(
        Bucket=FEEDBACK_BUCKET,
        Key=key,
        Body=json.dumps(feedback, ensure_ascii=False),
        ContentType="application/json",
    )