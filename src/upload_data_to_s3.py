"""This file uploads data by first querying them using the metadata and AWS GLue and Athena,
    then it uploads them to S3, after having sanitized the filename and made sure that the file doesn't already exist in S3
"""
import os
import logging
from dotenv import load_dotenv
import boto3
import re
from pyathena import connect
from pyathena.pandas.cursor import PandasCursor
from utils import sanitize_filename, sanitize_title, upload_file_from_url
from tqdm import tqdm

load_dotenv()

logging.basicConfig(level=logging.WARNING)

ATHENA_DB = "default"
ATHENA_OUTPUT = "s3://bfe-public-data-pdf/pdfs-batch-athena-queries/"
AWS_REGION = "eu-central-1"
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

cursor = connect(aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                s3_staging_dir=ATHENA_OUTPUT,
               region_name=AWS_REGION,
               cursor_class=PandasCursor).cursor()


query = """SELECT *
    FROM "default"."metadata_db" 
    WHERE date_type = 'pdf'
    ORDER BY date_parse(pub_date, '%d.%m.%Y') DESC 
    LIMIT 1000;
    """

df = cursor.execute(query).as_pandas()

print(f"Found {len(df)} URLs to download.")

print(df.head())

for row in tqdm(df.itertuples(index=False), total=len(df), desc="Uploading to S3"):
    sanitized_filename = sanitize_filename(row.title)
    row_metadata = {"pub_date": row.pub_date, "data_type" : row.date_type, "title" : sanitize_title(row.title), "lan": row.lan}

    upload_file_from_url(row.href, sanitized_filename, row_metadata)






