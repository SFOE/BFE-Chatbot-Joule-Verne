import os
from urllib.parse import urlparse
import streamlit as st
import boto3
import logging
import uuid
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY_ID = os.getenv("AWS_SECRET_ACCESS_KEY")

AGENT_ALIAS_ID = os.getenv("AGENT_ALIAS_ID")
AGENT_ID = os.getenv("AGENT_ID")

logging.basicConfig(level=logging.INFO)

bedrock_client = boto3.client('bedrock-agent-runtime',
                      region_name='eu-central-1',
                      aws_access_key_id = AWS_ACCESS_KEY_ID,
                      aws_secret_access_key=AWS_SECRET_KEY_ID,
                      verify=False #"custom_bundle.pem"
                      )
s3_client = boto3.client(
      's3',
      region_name='eu-central-1',
      aws_access_key_id = AWS_ACCESS_KEY_ID,
      aws_secret_access_key = AWS_SECRET_KEY_ID,
      verify=False
      )

def query_agent(prompt, session_id):
      response = bedrock_client.invoke_agent(
            agentAliasId = AGENT_ALIAS_ID,
            agentId = AGENT_ID,
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

session_id = st.session_state.get("session_id", str(uuid.uuid4()))
st.session_state["session_id"] = session_id

st.title(":zap: Demo BFE - Chatbot")

source_files = None

with st.form("my-form"):
      text = st.text_area(
            "Please enter your question : ",
            "Type your question here..."
      )
      submitted = st.form_submit_button("Submit")
      text = text.strip()
      
      if submitted :
            if not text or text=="Type your question here...":
                  st.write("Please enter your question before submitting")
             
            else:
                  with st.spinner('Your question is being processed'):
                        response = query_agent(text, st.session_state["session_id"])
                        for event in response.get("completion"):
                              
                              #Collect agent output.
                              if 'chunk' in event:
                                    chunk = event["chunk"]
                                    if chunk.get('attribution'):
                                          s3_refs = [refs_type["location"]["s3Location"]["uri"] for c in chunk["attribution"]["citations"]
                                                for refs_type in c["retrievedReferences"] if refs_type["location"]["type"]=="S3"]
                                          buckets, keys, source_files = zip(*[parse_s3_uri(uri) for uri in s3_refs])
                                          

                                    st.write(chunk['bytes'].decode())
                                    st.write(chunk['attribution'])
                                    
                              
                              # Log trace output.
                              if 'trace' in event:
                                    trace_event = event.get("trace")
                                    trace = trace_event['trace']
                                    for key, value in trace.items():
                                          logging.info("%s: %s",key,value)

if source_files:
      st.write("Sources:")
      for b, k, s in zip(buckets, keys, source_files):
            type_ = "application/pdf"
            if s.endswith('-parsed.txt'):
                  type_ = None
                  
            st.download_button(
                  label=f"{s}",
                  file_name=s,
                  key=k,
                  data = s3_client.get_object(Bucket=b, Key=k)['Body'].read(),
                  on_click='ignore',
                  icon="📁",
                  mime=type_
                  )

if st.button("Clear chat"):
      st.session_state["session_id"] = str(uuid.uuid4())