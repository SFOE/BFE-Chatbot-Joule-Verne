import os
import streamlit as st
import boto3
import logging
import uuid
from botocore.exceptions import ClientError

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY_ID = os.getenv("AWS_SECRET_ACCESS_KEY")

logging.basicConfig(level=logging.INFO)

client = boto3.client('bedrock-agent-runtime',
                      region_name='eu-central-1',
                      aws_access_key_id = AWS_ACCESS_KEY_ID,
                      aws_secret_access_key=AWS_SECRET_KEY_ID,
                      verify=False #"custom_bundle.pem"
                      )

def query_agent(prompt, session_id):
      response = client.invoke_agent(
            agentAliasId='KOKOM4FTJF',
            agentId='VHRROSBR5W',
            enableTrace=True,
            sessionId=session_id,
            inputText=prompt
      )
      return response

session_id = st.session_state.get("session_id", str(uuid.uuid4()))
st.session_state["session_id"] = session_id

st.title(":zap: Demo BFE - Chatbot")

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
                                    st.write(chunk["bytes"].decode())
                              
                              # Log trace output.
                              if 'trace' in event:
                                    trace_event = event.get("trace")
                                    trace = trace_event['trace']
                                    for key, value in trace.items():
                                          logging.info("%s: %s",key,value)

if st.button("Clear chat"):
      st.session_state["session_id"] = str(uuid.uuid4())