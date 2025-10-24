"""This file filters the data in the S3 bucket with all pdfs in a given time interval, and uploads them to the knowledge base.
It first uplaods them to a temporary S3 bucket, that is then erased"""

import boto3
from datetime import datetime

S3_BUCKET = "bfe-public-data-pdf"
S3_PREFIX = "pdfs-batch/"
S3_TEMP = "kb-upload_temp/"
KNOWLEDGE_BASE = "your-knowledge-base-id"
DATA_SOURCE = "your-data-source-id"


s3_client = boto3.client("s3")
bedrock_agent_client = boto3.client("bedrock-agent")

def filter_files_by_date(start_date:datetime=None, end_date:datetime=None) -> list:
    """We retrieve only files in the given time interval. If no interval is given, eg only end_date,
      we consider that we take all files until the end_date"""
    
    filtered_files =[]

    paginator = s3_client.get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(Bucket = S3_BUCKET, Prefix=S3_PREFIX)

    for page in page_iterator:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(".pdf"):
                head = s3_client.head_object(Bucket=S3_BUCKET, Key=key)
                pub_date = datetime.strptime(head['Metadata']['pub_date'], "%d.%m.%Y")
               
                if start_date and end_date:
                    if pub_date >= start_date and pub_date <= end_date:
                        filtered_files.append(key)
                elif start_date:
                    if pub_date >= start_date:
                        filtered_files.append(key)
                elif end_date:
                    if pub_date <= end_date:
                        filtered_files.append(key)
    return filtered_files

if __name__=="__main__":
    filtered_files = filter_files_by_date(start_date=datetime(2025,8,1))
    print(filtered_files)