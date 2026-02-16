import streamlit as st
import logging
import uuid
from src.utils import parse_s3_uri, query_agent, s3_get_object
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

source_files = None
s3_files = []
web_refs = []

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

with st.expander(":information_source: :construction:"):
    st.write("""
    This is a demo application and will still be submitted to changes. The chatbot might not always be correct or precise. Do not hesitate to check the sources in the side bar if unsure. Please be careful not to upload any personal data in the chat.
    For any questions or requests you can [contact us](mailto:digitalisierung@bfe.admin.ch) at the Digital Innovation & Geoinformation section :blush:
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
            st.chat_message("assistant").markdown("Please enter your question before submitting.")
            
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
                  if s.endswith('-parsedtxt'):
                        base_filename = s.rsplit("/", 1)[-1].replace("-parsedtxt", ".pdf")
                        pdf_subfolder = "pdfs-batch/"
                        k = pdf_subfolder + base_filename
                        s = base_filename
                        
                  st.sidebar.download_button(
                        label=f"{s}",
                        file_name=s,
                        key=k,
                        data = s3_get_object(b, k),
                        on_click='ignore',
                        icon="📃",
                        mime=type_
                        )

