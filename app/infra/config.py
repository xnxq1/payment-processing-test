from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="payment-processing", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    json_logs: bool = Field(default=True, alias="JSON_LOGS")

    api_key: str = Field(default="local-dev-api-key", alias="API_KEY")
    webhook_secret: str = Field(default="local-dev-webhook-secret", alias="WEBHOOK_SECRET")
    webhook_timeout_seconds: float = Field(default=5.0, alias="WEBHOOK_TIMEOUT_SECONDS")

    postgres_db: str = Field(default="payments", alias="POSTGRES_DB")
    postgres_user: str = Field(default="payments", alias="POSTGRES_USER")
    postgres_password: str = Field(default="payments", alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(default="postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, alias="REDIS_DB")

    rabbitmq_url: str = Field(
        default="amqp://guest:guest@rabbitmq:5672/",
        alias="RABBITMQ_URL",
    )
    rabbitmq_exchange: str = Field(default="payments", alias="RABBITMQ_EXCHANGE")
    consumer_prefetch: int = Field(default=10, alias="CONSUMER_PREFETCH")

    topic_payments_new: str = Field(default="payments.new", alias="QUEUE_PAYMENTS_NEW")
    topic_payments_retry: str = Field(default="payments.new.retry", alias="QUEUE_PAYMENTS_RETRY")
    topic_payments_dlq: str = Field(default="payments.new.dlq", alias="QUEUE_PAYMENTS_DLQ")

    payment_processing_min_seconds: float = Field(
        default=2.0,
        alias="PAYMENT_PROCESSING_MIN_SECONDS",
    )
    payment_processing_max_seconds: float = Field(
        default=5.0,
        alias="PAYMENT_PROCESSING_MAX_SECONDS",
    )
    payment_success_rate: float = Field(default=0.9, alias="PAYMENT_SUCCESS_RATE")
    payment_max_retries: int = Field(default=3, alias="PAYMENT_MAX_RETRIES")

    outbox_poll_interval_seconds: float = Field(
        default=1.0,
        alias="OUTBOX_POLL_INTERVAL_SECONDS",
    )
    outbox_batch_size: int = Field(default=50, alias="OUTBOX_BATCH_SIZE")

    @computed_field
    @property
    def _db_dsn(self) -> str:
        return (
            f"{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def db_url(self) -> str:
        return f"postgresql+psycopg://{self._db_dsn}"

    @computed_field
    @property
    def db_url_async(self) -> str:
        return f"postgresql+asyncpg://{self._db_dsn}"

    @computed_field
    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


def get_settings() -> Settings:
    return Settings()


settings = get_settings()
