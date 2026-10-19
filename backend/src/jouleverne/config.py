from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    ENVIRONMENT: str = "production"
    RATE_LIMIT: str = "100/minute"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173"]

    # AWS
    AWS_REGION: str = "eu-central-1"

    # AgentCore Runtime
    AGENTCORE_RUNTIME_ARN: str
    AGENTCORE_ENDPOINT_ARN: str = ""

    # S3 buckets
    FEEDBACK_BUCKET: str
    PDF_BUCKET: str
    EXTRACTED_BUCKET: str
    WEBSITE_BUCKET: str
    FEDLEX_BUCKET: str

    # Auth — comma-separated Cognito group names
    ALLOWED_COGNITO_GROUPS: str = ""

    # Knowledge base display names — comma-separated pairs
    # Multi-language: "id:DE_Name|FR_Name|IT_Name|EN_Name"
    # Single name (all locales): "id:Name"
    KB_DISPLAY_NAMES: str = ""

    # ------------------------------------------------------------------
    # Conversation history (persistent per-user chats)
    # ------------------------------------------------------------------
    # DynamoDB table holding the conversation index (one item per chat:
    # person_id/session_id/title/updated_at/mode_config) and per-user
    # preferences (the save opt-in flag). Empty => persistence disabled, the
    # app behaves exactly as before (ephemeral chats only).
    CONVERSATIONS_TABLE: str = ""

    # S3 bucket + prefix holding the full chat transcript JSON per conversation.
    # Reuses the feedback bucket; the Strands agent transcript lives under the
    # same sessions/ prefix. Empty bucket => persistence disabled.
    CONVERSATIONS_BUCKET: str = ""
    CONVERSATIONS_PREFIX: str = "sessions/"

    # Prefix for opt-out (short-lived) agent transcripts. Must match the agent's
    # EPHEMERAL_PREFIX. A dedicated 1-day S3 lifecycle rule guarantees cleanup
    # even if the active delete never fires.
    EPHEMERAL_PREFIX: str = "ephemeral/"

    # ------------------------------------------------------------------
    # Uploaded-document RAG (lightweight per-session index)
    # ------------------------------------------------------------------
    # Embedding model for indexing/searching uploaded chat documents. Same model
    # the knowledge bases use (multilingual DE/FR/IT/EN), so vector semantics are
    # consistent and the Bedrock invoke permission already exists for its ARN.
    EMBEDDING_MODEL_ID: str = "amazon.titan-embed-text-v2:0"
    EMBEDDING_DIMENSIONS: int = 1024

    # Size-based chunking (approx. token counts; ~4 chars/token). Kept close to
    # the KBs' 512/60 so chunk granularity matches the rest of the system.
    DOC_CHUNK_TOKENS: int = 512
    DOC_CHUNK_OVERLAP_TOKENS: int = 60

    # Number of chunks returned per document search.
    DOC_SEARCH_TOP_N: int = 5


settings = Settings()
