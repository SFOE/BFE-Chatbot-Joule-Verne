import boto3
from ..config import settings

agentcore_client = boto3.client(
    "bedrock-agentcore",
    region_name=settings.AWS_REGION,
)

s3_client = boto3.client(
    "s3",
    region_name=settings.AWS_REGION,
)

# DynamoDB resource (higher-level API) for the conversation index + user
# preferences table. Resource interface keeps item put/get/query concise.
dynamodb_resource = boto3.resource(
    "dynamodb",
    region_name=settings.AWS_REGION,
)

# Bedrock runtime for embeddings (uploaded-document RAG index).
bedrock_runtime_client = boto3.client(
    "bedrock-runtime",
    region_name=settings.AWS_REGION,
)
