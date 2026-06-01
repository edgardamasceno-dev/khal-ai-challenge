"""Configuracao da aplicacao (composition root le daqui)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://khal:khal_local_dev@database:5432/khal"
    kb_dir: str = "kb"

    # Object storage das faturas (MinIO/S3 — ADR-0009).
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "faturas"
    minio_secure: bool = False
    files_public_base_url: str = "http://localhost/files"  # proxy do gateway -> /files/{key}

    # Notificações proativas (SPEC-009 / ADR-0005).
    nats_url: str = "nats://nats:4222"
    omni_url: str = "http://omni:8882"  # REST do Omni (envio de texto); best-effort
    omni_api_key: str = ""
    # SPEC-030: o instance-id é dinâmico por pareamento — por isso NÃO se fixa no .env.
    # Vazio (default) = o backend resolve o UUID pelo NOME estável abaixo, em runtime.
    # Preencher só p/ forçar uma instância específica (override).
    omni_instance_id: str = ""
    omni_instance_name: str = "luzdovale-bot"  # nome estável p/ resolver o instance-id

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
