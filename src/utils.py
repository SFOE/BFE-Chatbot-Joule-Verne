import os
import re
import unicodedata
import boto3
from botocore.exceptions import ClientError
import requests
import io
from dotenv import load_dotenv

load_dotenv()

s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name='eu-central-1'
    )

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
        if e.response["Error"]["Code"] == "404":
            continue
        else:
            print(f"Error checking file: {e}")
            raise
    
    try:
        s3_client.upload_fileobj(pdf_buffer, Bucket=s3_bucket, Key=s3_key, ExtraArgs={"ContentType": "application/pdf", "Metadata" : metadata})
        return True
    except Exception as e:
        print(f"Failed to download file {sanitized_filename} to S3")
        raise
