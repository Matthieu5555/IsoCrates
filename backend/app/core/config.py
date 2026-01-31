"""Application configuration with validation."""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import List


class Settings(BaseSettings):
    """
    Application settings with validation.

    Uses Pydantic for configuration validation, preventing
    common security issues like wildcard CORS.
    """

    # CORS Configuration
    cors_allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:3001",
        description="Allowed CORS origins (comma-separated)"
    )

    # Database Configuration
    database_url: str = Field(
        default="sqlite:///./alto_isocrates.db",
        description="Database connection URL"
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

    # Rate Limiting
    # RATE_LIMIT_PER_MINUTE: max requests per client per minute. Applies per-IP or per-token.
    rate_limit_per_minute: int = Field(
        default=60,
        description="Maximum requests per client per minute"
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

    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow reading from environment variables with different case
        case_sensitive = False


# Global settings instance
settings = Settings()
