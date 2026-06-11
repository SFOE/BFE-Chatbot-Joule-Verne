import os
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