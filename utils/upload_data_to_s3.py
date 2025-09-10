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

load_dotenv()

logging.basicConfig(level=logging.DEBUG)

ATHENA_DB = "default"
ATHENA_OUTPUT = "s3://bfe-public-data-pdf/pdfs-batch-athena-queries/"
ATHENA_REGION = "eu-central-1"
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

conn = connect(aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                s3_staging_dir=ATHENA_OUTPUT,
               region_name=ATHENA_REGION,
               cursor_class=PandasCursor)

cursor = conn.cursor()

query = """SELECT *
    FROM "default"."metadata_db" 
    WHERE date_type = 'pdf'
    ORDER BY date_parse(pub_date, '%d.%m.%Y') DESC 
    LIMIT 1000;
    """

cursor.execute(query)
df = cursor.as_pandas()
print(df.head())

print(f"Found {len(df)} URLs to download.")


