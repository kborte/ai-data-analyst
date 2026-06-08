from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "ai-data-analyst-backend"
    ENV: str = "development"
    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_DIR: str = "storage/uploads"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
