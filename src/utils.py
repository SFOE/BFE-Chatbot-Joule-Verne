import os
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

def sanitize_filename(filename: str) -> str:
    forbidden_chars = r'\.\/:*?"“”<>«»|’,'
    text = ''.join(c for c in filename if c not in forbidden_chars)
    return text

def upload_file(filename, bucket, objname=None):
    if objname is None:
        objname = os.path.basename(filename)
        
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name='eu-central-1'
        )
    try:
        response = s3_client.upload_file(filename, bucket, objname)
    except ClientError as e:
        logging.error(e)
        return False
    return True
