from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "TaxLens AI"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "taxlens"
    database_user: str = "taxlens"
    database_password: str = "taxlens"
    local_storage_path: str = "./data/local"
    embedding_model_id: str = "intfloat/multilingual-e5-small"
    embedding_model_revision: str = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    embedding_model_path: str = "./data/models/multilingual-e5-small"
    embedding_dimensions: int = 384
    embedding_max_tokens: int = 512
    embedding_batch_size: int = 32
    ocr_enabled: bool = True
    ocr_language: str = "vie+eng"
    ocr_render_scale: float = 2.0
    ocr_timeout_seconds: float = 30.0
    hf_token: str | None = None
    hf_chat_base_url: str = "https://router.huggingface.co/v1"
    hf_chat_model: str = "Qwen/Qwen3-4B-Instruct-2507"
    hf_chat_routing_policy: str = "cheapest"
    hf_chat_timeout_seconds: float = 30.0
    hf_chat_max_output_tokens: int = 1400
    hf_chat_temperature: float = 0.1
    mlflow_enabled: bool = False
    mlflow_tracking_uri: str = "http://mlflow:5000"
    mlflow_experiment_name: str = "taxlens-qa"
    airflow_internal_token: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def database_url(self) -> str:
        return (
            "postgresql+psycopg://"
            f"{self.database_user}:{self.database_password}@"
            f"{self.database_host}:{self.database_port}/{self.database_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
