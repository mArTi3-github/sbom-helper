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


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    url: str = "postgresql://sbom:sbom@localhost:5432/sbom"
    pool_min_size: int = 2
    pool_max_size: int = 10


settings = Settings()
storage_settings = StorageSettings()


class SbomSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SBOM_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    max_file_size: int = 200 * 1024 * 1024  # 200 MB


sbom_settings = SbomSettings()
