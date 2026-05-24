from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PURL2REPO_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    timeout: float = 15.0
    use_cache: bool = True
    strict: bool = False
    no_network: bool = False
    cache_dir: str | None = None


settings = Settings()