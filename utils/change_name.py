
import os
from dotenv import load_dotenv
import boto3
import logging
import re
import pyathena

logging.basicConfig(level=logging.WARNING)

load_dotenv()

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

client = boto3.client(
      's3',
      region_name='eu-central-1',
      aws_access_key_id=AWS_ACCESS_KEY,
      aws_secret_access_key=AWS_SECRET_KEY
      )

all_objects = client.list_objects(
    Bucket = "bfe-public-data-pdf",

)

def sanitize_filename(filename: str) -> str:
    forbidden_chars = r'\.\/:*?"“”<>«»|’,'
    text = ''.join(c for c in filename if c not in forbidden_chars)
    return text

if __name__ == "__main__":
    obj_keys = [obj["Key"] for obj in all_objects['Contents'] if (obj["Key"].startswith("pdfs") and obj["Key"].endswith(".pdf"))]

    obj_keys = [re.sub(r"pdfs-batch\/", "", k) for k in obj_keys]
    obj_keys = [re.sub(r"\.pdf", "", k) for k in obj_keys]

    obj_keys = [key.replace(" ", "") for key in obj_keys]
    obj_keys = [key.replace("-", "") for key in obj_keys]
    obj_keys = [key.replace(r"\-", "") for key in obj_keys]
    obj_keys =[sanitize_filename(key).strip().lower() for key in obj_keys]
    print(obj_keys[:10])





