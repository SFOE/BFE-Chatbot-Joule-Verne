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

    # Specific (personal/group) knowledge bases selectable as a chat mode.
    # Same format as KB_DISPLAY_NAMES:
    # "id:DE_Name|FR_Name|IT_Name|EN_Name" or "id:Name"
    SPECIFIC_KB_DISPLAY_NAMES: str = ""


settings = Settings()
