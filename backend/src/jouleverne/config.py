from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

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

    # Knowledge base display names — comma-separated pairs "id:name,id:name"
    # If a KB ID isn't mapped, it shows as "Wissensdatenbank"
    KB_DISPLAY_NAMES: str = ""


settings = Settings()
