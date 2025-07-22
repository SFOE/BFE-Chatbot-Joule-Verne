import os
import logging
import json
import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)

def upload_file(filename, bucket, objname=None):
      if objname is None:
            objname = os.path.basename(filename)
            
      s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name='eu-central-1'
            )
      try:
            response = s3_client.upload_file(filename, bucket, objname)
      except ClientError as e:
            logging.error(e)
            return False
      return True

with open('./data/all_pdf_data.json', 'r') as input_file, open('./data/metadata.jsonl', 'w') as output_file:
      data =  json.load(input_file)
      for record in data:
            output_file.write(json.dumps(record) + '\n')
            

bucket_name = 'bfe-public-data-pdf'
object_key = 'metadata/metadata.jsonl'

# if upload_file('./data/metadata.jsonl', bucket_name, object_key):
#     print("File uploaded successfully!")
# else:
#     print("Failed to upload file.")   