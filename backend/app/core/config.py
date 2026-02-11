"""Application configuration with validation."""

from enum import Enum
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import List


class Environment(str, Enum):
    """Application environment."""
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class ConfigurationError(Exception):
    """Raised when application configuration is invalid for the environment."""
    pass


class Settings(BaseSettings):
    """
    Application settings with validation.

    Uses Pydantic for configuration validation, preventing
    common security issues like wildcard CORS.
    """

    # Environment
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Application environment (development/production)"
    )

    # CORS Configuration
    cors_allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:3001",
        description="Allowed CORS origins (comma-separated)"
    )

    # Database Configuration
    database_url: str = Field(
        default="sqlite:///./isocrates.db",
        description="Database connection URL"
    )
    # Connection pool tuning (PostgreSQL only; ignored for SQLite).
    # Each persistent connection uses ~5-10 MB on the server.
    db_pool_size: int = Field(
        default=5,
        description="Number of persistent database connections"
    )
    db_max_overflow: int = Field(
        default=10,
        description="Extra connections allowed during traffic bursts"
    )
    db_pool_timeout: int = Field(
        default=30,
        description="Seconds to wait for a connection from the pool before raising"
    )
    db_pool_recycle: int = Field(
        default=1800,
        description="Seconds before a connection is recycled (prevents stale connections)"
    )

    # Webhook Configuration
    # HMAC secret for validating GitHub webhook signatures
    # Set via GITHUB_WEBHOOK_SECRET env var; leave empty to skip verification (dev only)
    github_webhook_secret: str = Field(
        default="",
        description="GitHub webhook secret for HMAC signature verification"
    )

    # Authentication
    # JWT_SECRET_KEY: signing key for service tokens. Default is insecure — override in production.
    # AUTH_ENABLED: when False, all endpoints accept unauthenticated requests (dev mode).
    jwt_secret_key: str = Field(
        default="dev-insecure-key-change-me",
        description="JWT signing secret (override in production)"
    )
    jwt_algorithm: str = Field(default="HS256")
    auth_enabled: bool = Field(
        default=False,
        description="Enable JWT authentication (False for development)"
    )

    # Audit Log Retention
    audit_retention_days: int = Field(
        default=365,
        description="Days to keep audit log entries (0 = keep forever)"
    )

    # Rate Limiting
    # RATE_LIMIT_PER_MINUTE: max requests per client per minute. Applies per-IP or per-token.
    rate_limit_per_minute: int = Field(
        default=60,
        description="Maximum requests per client per minute"
    )

    # Embedding Configuration (for semantic search)
    # LiteLLM model string, e.g. "openai/text-embedding-3-small", "cohere/embed-english-v3.0"
    # Empty string = embeddings disabled (search falls back to FTS only)
    embedding_model: str = Field(
        default="",
        description="LiteLLM model string for embeddings (empty = disabled)"
    )
    embedding_api_key: str = Field(
        default="",
        description="API key for embedding provider"
    )
    embedding_api_base: str = Field(
        default="",
        description="Base URL for embedding provider (optional)"
    )
    embedding_dimensions: int = Field(
        default=0,
        description="Embedding vector dimensions (0 = use model default)"
    )

    # Chat / RAG Configuration
    # LiteLLM model string for RAG chat completions.
    # Empty string = chat disabled.
    chat_model: str = Field(
        default="",
        description="LiteLLM model for RAG chat completions (empty = disabled)"
    )
    chat_api_key: str = Field(
        default="",
        description="API key for chat provider (falls back to embedding_api_key if empty)"
    )
    chat_api_base: str = Field(
        default="",
        description="Base URL for chat provider (optional, for custom endpoints)"
    )
    chat_max_context_docs: int = Field(
        default=5,
        description="Max documents to include as RAG context"
    )

    # Logging Configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    log_format: str = Field(
        default="json",
        description="Log output format: 'json' for structured, 'text' for human-readable"
    )

    def get_cors_origins(self) -> List[str]:
        """
        Get CORS origins as a list.

        Parses comma-separated string and validates no wildcards.
        """
        origins = [origin.strip() for origin in self.cors_allowed_origins.split(',') if origin.strip()]

        # SECURITY: Prevent wildcard CORS
        if "*" in origins:
            raise ValueError(
                "Wildcard CORS (*) not allowed. "
                "Specify explicit origins in CORS_ALLOWED_ORIGINS"
            )

        return origins

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the standard Python logging levels."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of: {valid_levels}")
        return v_upper

    def validate_production_config(self) -> None:
        """Validate configuration for production environment.

        In production, fails startup if security-critical settings use insecure defaults.
        In development, logs warnings but allows startup.

        Raises:
            ConfigurationError: If production config is insecure.
        """
        errors: list[str] = []

        # Check JWT secret
        if self.jwt_secret_key == "dev-insecure-key-change-me":
            errors.append(
                "JWT_SECRET_KEY is using the default insecure value. "
                "Generate a secure key: openssl rand -hex 32"
            )

        # Check authentication is enabled
        if not self.auth_enabled:
            errors.append(
                "AUTH_ENABLED is false. "
                "Authentication must be enabled in production."
            )

        # Check for localhost CORS origins
        origins = self.get_cors_origins()
        localhost_origins = [o for o in origins if "localhost" in o or "127.0.0.1" in o]
        if localhost_origins:
            errors.append(
                f"CORS allows localhost origins: {localhost_origins}. "
                "Remove localhost origins for production."
            )

        if errors:
            if self.environment == Environment.PRODUCTION:
                raise ConfigurationError(
                    "Production configuration is insecure:\n  - " + "\n  - ".join(errors)
                )
            # In development, just return — main.py will log warnings
            return

    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow reading from environment variables with different case
        case_sensitive = False


# Global settings instance
settings = Settings()
