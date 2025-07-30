import os
import logging
import asyncio
import boto3
from botocore.exceptions import ClientError
import pandas as pd
import io
import requests
import re
from tqdm import tqdm
from dotenv import load_dotenv
from llama_index.core import SimpleDirectoryReader
from llama_parse import LlamaParse
from s3fs import S3FileSystem

load_dotenv()

logging.basicConfig(level=logging.INFO)

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
LLAMA_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY")

client = boto3.client(
      's3',
      region_name='eu-central-1',
      aws_access_key_id=AWS_ACCESS_KEY,
      aws_secret_access_key=AWS_SECRET_KEY
      )

response = client.get_object(
      Bucket="bfe-public-data-pdf",
      Key="metadata/small-set-public-data-pdf/f92a1fe9-d29e-4306-b50f-6c8a99e342b6.csv"
)

content = response['Body'].read().decode('utf-8')
metadata_df = pd.read_csv(io.StringIO(content))

base_url  ="https://www.bfe.admin.ch"
bucket = "bfe-public-data-pdf"
obj = "pdfs-batch/"
local_path = "./data/batches/batch_1/"


def fetch_metadata():
      documents =  SimpleDirectoryReader(local_path).load_data(num_workers=3, show_progress=True)
      return documents
      
           
async def main():
      docs = fetch_metadata()
      
      for doc in docs:
            filename = getattr(doc, 'filename', '') 
            doc_filename = os.path.splitext(os.path.basename(filename))[0].strip().lower()
            
            for _, row in metadata_df.iterrows():
                  if row['title'] == doc_filename:
                        doc.metadata['language'] = row['lan']
                        doc.metadata['title'] = row['title']
                        doc.metadata['publication_date'] = row['pub_date']
                        doc.metadata['data_type'] = row['date_type']
                        break
      
      parser = LlamaParse(
            api_key=LLAMA_API_KEY,
            custom_client=client,
            num_workers=3,
            show_progress=True
      )
      
      parsed_docs = await parser.aparse(docs)
      
      tasks

      

if __name__=='__main__':
      asyncio.run(main())

