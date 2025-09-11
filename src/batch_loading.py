"""This was used for parsing the files by batches using LlamaParser (not an optimal solution for autmoation)"""
import os
import logging
import urllib
import asyncio
from asyncio import Semaphore
import httpx
import boto3
import aioboto3
from botocore.exceptions import ClientError
import pandas as pd
import io
from unidecode import unidecode
from tqdm.asyncio import tqdm_asyncio
from dotenv import load_dotenv
from collections import defaultdict
from llama_index.core import Document
from llama_parse import LlamaParse
from dataclasses import dataclass


load_dotenv()

logging.basicConfig(level=logging.WARNING)

proxies = urllib.request.getproxies()
proxies_dict = {}
if 'https' in proxies:
      proxies_dict["https://"] = proxies['https']
if 'http' in proxies:
      proxies_dict["http://"] = proxies['http']

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

@dataclass
class File:
      filename: str
      filepath: str
      metadata: dict

def load_data_from_directory(directory:str, input_files:list=None):
      files = []
      if input_files:
            for file in input_files:
                  filepath = os.path.join(directory, file)
                  files.append(File(file, filepath, get_metadata(file)))
      else:
            for file in os.listdir(directory):
                  filepath = os.path.join(directory, file)
                  files.append(File(file, filepath, get_metadata(file)))
      return files
                  

async def parsing_document(http_client, doc):

      parser = LlamaParse(
            api_key=LLAMA_API_KEY,
            custom_client=http_client,
            num_workers=2,
            show_progress=True,
            verbose=False
      )
      parsed_result = await parser.aparse(doc)
      return parsed_result

semaphore = Semaphore(2)
async def get_parsed_doc(doc):
      async with semaphore:
            async with httpx.AsyncClient(verify=False) as http_client:
                  client.proxies = proxies_dict
                  results = await parsing_document(http_client, doc)
            if results:
                  return results
            else:
                  raise Exception("No documents were correctly parsed and returned")

async def uploading_to_s3(doc):
      title = doc.metadata['title'].strip().lower().replace(' ', '-')
      title = title.replace('---', '-').replace("'", "-")
      s3_key = f"parsed-pdf-batch/{title}-parsed.txt"
      
      doc_text = doc.text
      
      metadata = {str(k): unidecode(str(v).strip().lower().replace(' ', '-')) for k,v in doc.metadata.items()}
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
                        Body=doc_text.encode("utf-8"),
                        Metadata=metadata
                  )
                  logging.info(f"Uploaded parsed doc successfully to s3://{bucket}/{s3_key}")
      except ClientError as e:
            logging.error(f"Failed to upload {s3_key} to S3: {e.response['Error']['Message']}")


def get_metadata(filename):
      index = filename.rfind('.pdf')
      doc_filename = filename[:index]
      doc_filename = sanitize_filename(doc_filename).strip().lower().replace(' ', '')
      metadata =  defaultdict()
      for _, row in metadata_df.iterrows():
            
            title = sanitize_filename(row['title']).strip().lower().replace(' ', '')
            if title == doc_filename:

                  metadata['language'] = row['lan']
                  metadata['title'] = sanitize_filename(row['title'])
                  metadata['publication_date'] = row['pub_date']
                  metadata['data_type'] = row['date_type']
                  break

      assert title == doc_filename
      return metadata  
           
async def main():
      data = load_data_from_directory(local_path)
      docs = [d.filepath for d in data[400:]]
      metadata = [d.metadata for d in data[400:]]
      
      print("Parsing documents:")
      parsed_results = await tqdm_asyncio.gather(
            *(get_parsed_doc(doc) for doc in docs), desc="Parsing", unit="doc"
      )
      documents = [Document(text="\n\n".join(page.text for page in result.pages), metadata= meta) for result, meta in zip(parsed_results, metadata)]
      #print(documents[0].text)
      print("Uploading to S3:")
      await tqdm_asyncio.gather(
            *(uploading_to_s3(doc) for doc in documents), desc="Uploading", unit="file"
      )


if __name__=='__main__':
      asyncio.run(main())