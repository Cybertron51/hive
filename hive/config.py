from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    akashml_api_key: str = ""
    akashml_base_url: str = "https://api.akashml.com/v1"
    akashml_model_small: str = ""
    akashml_model_large: str = ""
    senso_api_key: str = ""
    senso_base_url: str = "https://apiv2.senso.ai/api/v1"
    clickhouse_url: str = "http://localhost:8123"
    clickhouse_db: str = "hive"


settings = Settings()
