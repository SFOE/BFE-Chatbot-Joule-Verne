import boto3
from botocore.config import Config
from ..config import settings

agentcore_client = boto3.client(
    "bedrock-agentcore",
    region_name=settings.AWS_REGION,
)

s3_client = boto3.client(
    "s3",
    region_name=settings.AWS_REGION,
    config=Config(
        signature_version="s3v4",
        s3={"addressing_style": "virtual"},
    ),
)
