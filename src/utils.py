import os
import re
import unicodedata
from urllib.parse import urlparse
import boto3
from botocore.exceptions import ClientError
import requests
import io
import datetime as datetime
from tqdm import tqdm
from dotenv import load_dotenv
import logging

 
 
logging.basicConfig(level=logging.DEBUG)
 
st_logger = logging.getLogger("streamlit")
st_logger.setLevel(logging.INFO)
 

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION")
AGENT_ALIAS_ID = os.getenv("AGENT_ALIAS_ID")
AGENT_ID = os.getenv("AGENT_ID")


s3_client = boto3.client(
    's3',
    region_name=AWS_REGION
    )

bedrock_client = boto3.client(
    'bedrock-agent-runtime',
    region_name=AWS_REGION
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

def s3_get_object(bucket, key):
    return s3_client.get_object(Bucket=bucket, Key=key)['Body'].read()

def sanitize_filename(filename: str) -> str:
    forbidden_chars = r'\.\/:*?"“”<>«»|–’,'
    
    # Normalize Unicode characters to ASCII, stripping accents
    normalized = unicodedata.normalize('NFKD', filename)
    ascii_str = normalized.encode('ascii', 'ignore').decode('ascii')
    
    # Remove forbidden characters
    cleaned = ''.join(c for c in ascii_str if c not in forbidden_chars)
    
    # Replace spaces with hyphens, lowercase, strip leading/trailing spaces/hyphens
    cleaned = re.sub(r'\s+', '-', cleaned).strip().lower()
    
    # Replace multiple hyphens with a single hyphen
    cleaned = re.sub(r'-{2,}', '-', cleaned)
    
    return cleaned

def sanitize_title(title:str) -> str:
    normalized = unicodedata.normalize('NFKD', title)
    ascii_str = normalized.encode('ascii', 'ignore').decode('ascii')
    return ascii_str


def upload_file(filename, bucket, objname=None):
    """Uploads local file to S3"""
    if objname is None:
        objname = os.path.basename(filename)
        
    try:
        response = s3_client.upload_file(filename, bucket, objname)
    except ClientError as e:
        logging.error(e)
        return False
    return True

def upload_file_from_url(url, sanitized_filename, metadata):
    """Uploads file from an url to S3"""

    base_url = "https://www.bfe.admin.ch"
    response = requests.get(base_url + url)
    response.raise_for_status()
    pdf_buffer = io.BytesIO(response.content)

    s3_key = f"pdfs-batch/{sanitized_filename}.pdf"
    s3_bucket = "bfe-public-data-pdf"

    
    try:
        s3_client.head_object(Bucket=s3_bucket, Key=s3_key)
        print(f"File already exists at s3://{s3_bucket}/{s3_key}. Skipping it")
        return False
    except ClientError as e:
        error_code = e.response["Error"]["Code"] 
        if error_code != "404":
            print(f"Error checking file: {e}")
            raise
    
    try:
        s3_client.upload_fileobj(pdf_buffer, Bucket=s3_bucket, Key=s3_key, ExtraArgs={"ContentType": "application/pdf", "Metadata" : metadata})
        return True
    except Exception as e:
        print(f"Failed to download file {sanitized_filename} to S3")
        raise

def change_filenames():
    """Changes the filenames in S3 bucket for the parsed files (to do once- DONE)"""
    s3_bucket = "bfe-public-data-pdf"
    subfolder = "parsed-pdf-batch/"

    response = s3_client.list_objects_v2(Bucket=s3_bucket, Prefix=subfolder)

    for obj in tqdm(response.get("Contents", []), total = len(response.get("Contents", [])), desc="Changing parsed files' names"):
        old_key = obj["Key"]
        filename = old_key.split("/")[-1]
        new_filename = sanitize_filename(filename)
        new_key = subfolder + new_filename

        if old_key != new_key:
            s3_client.copy_object(Bucket=s3_bucket, CopySource={"Bucket": s3_bucket, "Key": old_key}, Key=new_key)
            s3_client.delete_object(Bucket=s3_bucket, Key=old_key)
        
def give_oldest_file_date():
    S3_BUCKET = "bfe-public-data-pdf"
    S3_PREFIX = "pdfs-batch/"

    paginator = s3_client.get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(Bucket = S3_BUCKET, Prefix=S3_PREFIX)

    oldest_time = datetime(2026,1,1)
    oldest_file = None
    for page in page_iterator:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            head = s3_client.head_object(Bucket=S3_BUCKET, Key=key)
            pub_date = datetime.strptime(head['Metadata']['pub_date'], "%d.%m.%Y")
        
            if pub_date < oldest_time:
                oldest_time = pub_date
                oldest_file = key

    return oldest_time, oldest_file
    
if __name__=="__main__":
    pass
    # change_filenames()
