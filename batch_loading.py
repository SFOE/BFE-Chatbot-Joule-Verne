import os
import logging
import asyncio
import boto3
import aioboto3
from botocore.exceptions import ClientError
import pandas as pd
import io
from tqdm.asyncio import tqdm_asyncio
from dotenv import load_dotenv
from llama_index.core import SimpleDirectoryReader
from llama_parse import LlamaParse

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
# obj = "pdfs-batch/"
local_path = "./data/batches/batch_1/"


def fetch_metadata():
      documents =  SimpleDirectoryReader(local_path).load_data(num_workers=3, show_progress=True)
      return documents

async def parsing_document(doc):
      filename = getattr(doc, 'filename', '') 
      doc_filename = os.path.splitext(os.path.basename(filename))[0].strip().lower()
            
      for _, row in metadata_df.iterrows():
            if row['title'].strip().lower() == doc_filename:
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
      
      parsed_result = await parser.aparse(doc)
      return parsed_result

async def uploading_to_s3(doc):
      s3_key = f"parsed-pdf-batch/{doc.metadata['title']}_parsed.txt"
      
      if hasattr(doc, "get_text_documents"):
            doc_texts = doc.get_text_documents(split_by_page=False)
            doc_text = "\n".join([t.text for t in doc_texts])
      else:
            doc_text = str(doc)
      
      try:
            session = aioboto3.Session()
            async with session.client(
                  's3',
                  region_name='eu-central-1',
                  aws_access_key_id=AWS_ACCESS_KEY,
                  aws_secret_access_key=AWS_SECRET_KEY
                  ) as client:
                  
                  await client.put_object(
                        Bucket=bucket,
                        Key=s3_key,
                        Body=doc_text.encode("utf-8")
                  )
                  logging.info(f"Uploaded parsed doc successfully to s3://{bucket}/{s3_key}")
      except ClientError as e:
            logging.error(f"Failed to upload {s3_key} to S3: {e.response['Error']['Message']}")
            
            
           
async def main():
      docs = fetch_metadata()
      
      print("Parsing documents:")
      parsed_results = await tqdm_asyncio.gather(
            *(parsing_document(doc) for doc in docs), desc="Parsing", unit="doc"
      )

      print("Uploading to S3:")
      await tqdm_asyncio.gather(
            *(uploading_to_s3(doc) for doc in parsed_results), desc="Uploading", unit="file"
      )


if __name__=='__main__':
      asyncio.run(main())