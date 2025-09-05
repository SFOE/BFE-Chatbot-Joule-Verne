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

source_files = None
s3_files = []
web_refs = []

session_id = st.session_state.get("session_id", str(uuid.uuid4()))
st.session_state["session_id"] = session_id

if "messages" not in st.session_state:
      st.session_state.messages = []

st.title("Demo BFE - Chatbot :zap:")

with st.expander(":information_source: :construction:"):
    st.write("""
    This is a demo application and will still be submitted to changes. The chatbot might not always be correct or precise. Do not hesitate to check the sources in the side bar if unsure.
    For any questions or requests you can [contact us](mailto:zoe.jeandupeux@bfe.admin.ch) at the Digital Innovation & Geoinformation section :blush:
    """)

for message in st.session_state.messages:
      with st.chat_message(message["role"]):
            st.markdown(message["content"])

st.sidebar.write("**Settings**  :pushpin:")

keep_session = st.sidebar.toggle("Session history", value=True, key="keep_session")

if not keep_session:
      st.session_state["session_id"] = str(uuid.uuid4())

if st.sidebar.button("Clear chat", icon="✏️"):
      st.session_state["messages"] = []
      st.rerun()
      
prompt = st.chat_input(
      "Type your question here..."
)

if prompt:
      if prompt.strip() == "": 
            st.chat_message("jv", avatar=st.image("./img/bundesamt_logo.jpeg")).markdown("Please enter your question before submitting")
            
      else:
            st.chat_message("user").markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})

            with st.spinner('Your question is being processed'):
                  response = query_agent(prompt, st.session_state["session_id"])
                  for event in response.get("completion"):
                        
                        #Collect agent output.
                        if 'chunk' in event:
                              chunk = event["chunk"]
                              if chunk.get('attribution'):
                                    for c in chunk['attribution']['citations']:

                                          s3_refs = [refs_type["location"]["s3Location"]["uri"]
                                                for refs_type in c["retrievedReferences"] if refs_type["location"]["type"]=="S3"]
                                          if s3_refs:
                                                s3_refs = set(s3_refs)
                                                buckets, keys, s3_files = zip(*[parse_s3_uri(uri) for uri in s3_refs])
                                          web_refs = [refs_type["location"]["webLocation"]["url"]
                                                for refs_type in c["retrievedReferences"] if refs_type["location"]["type"]=="WEB"]
                                          web_refs = set(web_refs)

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

st.sidebar.write("**Sources** :bulb:")
if s3_files or web_refs:
      
      if web_refs:
            for web in web_refs:
                  st.sidebar.write(web)
            
      if s3_files:
            for b, k, s in zip(buckets, keys, s3_files):
                  type_ = "application/pdf"
                  if s.endswith('-parsed.txt'):
                        type_ = None
                        
                  st.sidebar.download_button(
                        label=f"{s}",
                        file_name=s,
                        key=k,
                        data = s3_client.get_object(Bucket=b, Key=k)['Body'].read(),
                        on_click='ignore',
                        icon="📃",
                        mime=type_
                        )

