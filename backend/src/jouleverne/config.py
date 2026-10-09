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

<<<<<<< HEAD
=======
    # Specific (personal/group) knowledge bases selectable as a chat mode.
    # Format: "id:prefix:DE_Name|FR_Name|IT_Name|EN_Name" or "id:prefix:Name"
    # The prefix is the S3 folder the KB ingests from (used for uploads).
    SPECIFIC_KB_DISPLAY_NAMES: str = ""

    # S3 bucket holding the original uploaded documents for specific
    # (personal/group) KBs. This is the immutable "inbox" and the source of
    # truth for downloads/citations.
    SPECIFIC_KBS_BUCKET: str = ""

    # S3 bucket holding the processed/extracted content the specific KBs sync
    # from (extracted .txt / _partN.txt, passthrough copies, crawled website
    # text). Citations reference objects here; the backend maps them back to the
    # original file in SPECIFIC_KBS_BUCKET via each object's ".metadata.json"
    # sidecar (original_key attribute).
    SPECIFIC_KBS_EXTRACTED_BUCKET: str = ""

    # Presigned upload URL expiration in seconds
    UPLOAD_URL_EXPIRATION: int = 900

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

>>>>>>> 8cdf295 (give possibility to choose to store the chats)

settings = Settings()
