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

    # Per-KB write (upload + delete) allowlist by e-mail.
    # Format: "kb_id:email1|email2, kb_id2:email3"
    # A KB not listed here has NO write restriction (open to any authenticated
    # user). A KB listed with an empty list blocks all writes. Matching is
    # case-insensitive on the e-mail. Empty setting = current behaviour (open).
    UPLOAD_ALLOWED_EMAILS_BY_KB: str = ""

    # Knowledge base display names — comma-separated pairs
    # Multi-language: "id:DE_Name|FR_Name|IT_Name|EN_Name"
    # Single name (all locales): "id:Name"
    KB_DISPLAY_NAMES: str = ""

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


settings = Settings()
