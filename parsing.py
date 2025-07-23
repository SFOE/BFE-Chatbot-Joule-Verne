import os
import boto3
import pandas as pd
import io
import requests
import re
from tqdm import tqdm

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

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

for _, row in tqdm(metadata_df.iterrows()):
      response = requests.get(base_url + row['href'])
      os.makedirs('./data/batches/batch_1', exist_ok=True)
      title = row['title'].strip().replace(' ', '')
      title = re.sub(r'[\/\\\?\%\*\:\|\"<>\.]', '', title)
      
      with open(f"./data/batches/batch_1/{title}.pdf", 'wb') as f:
           f.write(response.content)
