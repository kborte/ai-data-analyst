from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "ai-data-analyst-backend"
    ENV: str = "development"
    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_DIR: str = "storage/uploads"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ai_data_analyst"
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "ai-data-analyst"
    STORAGE_TEMP_DIR: str = "/tmp/ai_data_analyst"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
