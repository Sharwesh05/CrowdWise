"""Application configuration.

Every value comes from the environment (or a .env file). No secret is ever
hardcoded here — defaults are only safe development placeholders, and the
security-sensitive ones are validated at startup when ENVIRONMENT=production.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- Core ----------
    app_name: str = "CrowdWise"
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    demo_mode: bool = True

    # ---------- Database ----------
    database_url: str = "sqlite+pysqlite:///./crowdwise.db"

    # ---------- Auth ----------
    jwt_secret: str = "dev-only-insecure-jwt-secret-change-me"
    cookie_secret: str = "dev-only-insecure-cookie-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    refresh_token_days: int = 14
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None
    access_cookie_name: str = "cw_access"
    refresh_cookie_name: str = "cw_refresh"
    csrf_cookie_name: str = "cw_csrf"

    # ---------- URLs ----------
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    # localhost and 127.0.0.1 are different origins to a browser; allow both
    # so the app works whichever one the developer opens.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ---------- Payments ----------
    payment_provider: Literal["demo", "razorpay"] = "demo"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    application_fee_amount: float = 500.0
    currency: str = "INR"

    # ---------- AI ----------
    # Every option below speaks the same OpenAI-compatible chat API; only the
    # endpoint, key and model differ. `nvidia` targets NVIDIA NIM (the hosted
    # build.nvidia.com gateway by default, or a self-hosted NIM container).
    ai_provider: Literal["mock", "gemma", "nvidia"] = "mock"
    gemma_provider: str = "openai_compatible"
    gemma_base_url: str = "http://localhost:11434/v1"
    gemma_api_key: str = ""
    gemma_model: str = "gemma3:4b"
    gemma_timeout_seconds: int = 60

    # ---------- AI: NVIDIA NIM ----------
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_api_key: str = ""
    nvidia_model: str = "deepseek-ai/deepseek-v4-pro-0813"
    nvidia_timeout_seconds: int = 90
    # The request body is model + messages only unless you opt into more.
    # `auto` asks plainly first and retries with response_format only if the
    # reply could not be parsed; `on` always sends it, `off` never does.
    nvidia_json_mode: Literal["auto", "on", "off"] = "auto"
    # 0 / unset omits the field. Reasoning models need no cap and are truncated
    # mid-thought by one meant for a plain instruct model.
    nvidia_max_tokens: int = 0
    nvidia_temperature: float | None = None

    # ---------- Sentiment ----------
    # `nvidia` reuses the NVIDIA_* settings above and classifies in batches.
    sentiment_provider: Literal["mock", "xlm-roberta", "nvidia"] = "mock"
    sentiment_model: str = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
    sentiment_device: str = "cpu"
    community_insight_refresh_threshold: int = 5

    # ---------- Blockchain ----------
    blockchain_provider: Literal["mock", "web3"] = "mock"
    blockchain_network: str = "hardhat-local"
    blockchain_rpc_url: str = "http://localhost:8545"
    blockchain_private_key: str = ""
    contract_address: str = ""
    blockchain_chain_id: int = 31337
    blockchain_explorer_url: str = ""
    chain_hash_salt: str = "dev-only-chain-hash-salt"

    # ---------- Storage ----------
    storage_provider: Literal["local", "s3"] = "local"
    storage_local_dir: str = "./storage"
    storage_endpoint: str = ""
    storage_bucket: str = "crowdwise"
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_region: str = "auto"
    storage_public_base_url: str = ""
    max_upload_mb: int = 10

    # ---------- KYC ----------
    kyc_provider: Literal["demo"] = "demo"

    # ---------- Rate limiting ----------
    rate_limit_auth_per_minute: int = 10
    rate_limit_default_per_minute: int = 120

    # ---------- Governance defaults ----------
    governance_duration_hours: int = 72
    governance_extension_days: int = 30

    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, value: str) -> str:
        return value.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def assert_production_safe(self) -> None:
        """Fail loudly rather than run production on development secrets."""
        if not self.is_production:
            return
        problems: list[str] = []
        if "dev-only" in self.jwt_secret or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be a strong non-default value")
        if "dev-only" in self.cookie_secret or len(self.cookie_secret) < 32:
            problems.append("COOKIE_SECRET must be a strong non-default value")
        if "dev-only" in self.chain_hash_salt:
            problems.append("CHAIN_HASH_SALT must be a non-default value")
        if self.demo_mode:
            problems.append("DEMO_MODE must be false in production")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true in production")
        if self.payment_provider == "razorpay" and not self.razorpay_webhook_secret:
            problems.append("RAZORPAY_WEBHOOK_SECRET is required")
        if self.ai_provider == "nvidia" and not self.nvidia_api_key:
            problems.append("NVIDIA_API_KEY is required when AI_PROVIDER=nvidia")
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
