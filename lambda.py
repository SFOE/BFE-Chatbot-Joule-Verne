from dotenv import load_dotenv
import streamlit as st
import boto3
import logging
from botocore.exceptions import ClientError

load_dotenv()

logging.basicConfig(level=logging.INFO)

client = boto3.client('bedrock-agent-runtime', region_name='eu-central-1')

def query_agent(prompt):
      response = client.invoke_agent(
            agentAliasId='KOKOM4FTJF',
            agentId='VHRROSBR5W',
            enableTrace=True,
            sessionId='114',
            inputText=prompt
      )
      return response

st.title("Demo BFE - Chatbot")

with st.form("my-form"):
      text = st.text_area(
            "Please enter your question : ",
            "Type your question here..."
      )
      submitted = st.form_submit_button("Submit")
      if submitted:
            response = query_agent(text)
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