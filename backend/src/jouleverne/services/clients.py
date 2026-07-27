import boto3
from ..config import settings

bedrock_client = boto3.client(
    "bedrock-agent-runtime",
    region_name=settings.AWS_REGION,
)

s3_client = boto3.client(
    "s3",
    region_name=settings.AWS_REGION,
)
