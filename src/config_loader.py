"""Configuration loader with YAML defaults and environment variable overlays."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class EmailConfig:
    """Email server configuration.

    Args:
        imap_host: IMAP server hostname.
        imap_port: IMAP server port.
        address: Email address for login.
        password: Email password.
        search_subject: Subject filter for invoice emails.
        folder: Mailbox folder to monitor.
    """

    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    address: str = ""
    password: str = ""
    search_subject: str = "Invoice"
    folder: str = "INBOX"


@dataclass
class DatabaseConfig:
    """Database connection configuration.

    Args:
        host: Database server hostname.
        port: Database server port.
        name: Database name.
        user: Database user.
        password: Database password.
    """

    host: str = "localhost"
    port: int = 5432
    name: str = "invoice_automation"
    user: str = "postgres"
    password: str = ""

    @property
    def url(self) -> str:
        """Construct SQLAlchemy database URL."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class SlackConfig:
    """Slack notification configuration.

    Args:
        webhook_url: Slack incoming webhook URL.
        enabled: Whether Slack notifications are enabled.
        channel: Default channel override (optional).
    """

    webhook_url: str = ""
    enabled: bool = True
    channel: str | None = None


@dataclass
class RetryConfig:
    """Retry behavior configuration.

    Args:
        max_attempts: Maximum number of retry attempts.
        base_delay: Base delay in seconds between retries.
        max_delay: Maximum delay in seconds between retries.
        exponential_base: Base for exponential backoff calculation.
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0


@dataclass
class MetricsConfig:
    """Prometheus metrics configuration.

    Args:
        enabled: Whether metrics collection is enabled.
        port: Port for the metrics HTTP server.
    """

    enabled: bool = False
    port: int = 9090


@dataclass
class StorageConfig:
    """AWS S3 storage configuration.

    Args:
        bucket_name: S3 bucket for document archival.
        region: AWS region.
        access_key_id: AWS access key ID.
        secret_access_key: AWS secret access key.
    """

    bucket_name: str = "invoice-archive"
    region: str = "us-east-1"
    access_key_id: str = ""
    secret_access_key: str = ""


@dataclass
class ValidationConfig:
    """Validation rules configuration.

    Args:
        max_invoice_amount: Maximum allowed invoice amount.
        min_invoice_amount: Minimum allowed invoice amount.
        po_numbers_file: Path to PO numbers reference CSV.
        approved_vendors_file: Path to approved vendors reference CSV.
        max_invoice_age_days: Maximum age of invoice date in days.
    """

    max_invoice_amount: float = 1_000_000.00
    min_invoice_amount: float = 0.01
    po_numbers_file: str = "config/po_numbers.csv"
    approved_vendors_file: str = "config/approved_vendors.csv"
    max_invoice_age_days: int = 365


@dataclass
class LoggingConfig:
    """Logging configuration.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        log_dir: Directory for log files.
        max_bytes: Maximum log file size before rotation.
        backup_count: Number of rotated log files to keep.
        json_format: Whether to use JSON log format.
    """

    level: str = "INFO"
    log_dir: str = "logs"
    max_bytes: int = 10_485_760  # 10 MB
    backup_count: int = 5
    json_format: bool = True


@dataclass
class AppConfig:
    """Root application configuration.

    Args:
        email: Email server configuration.
        database: Database connection configuration.
        slack: Slack notification configuration.
        retry: Retry behavior configuration.
        metrics: Prometheus metrics configuration.
        storage: AWS S3 storage configuration.
        validation: Validation rules configuration.
        logging: Logging configuration.
        dry_run: Whether to run in dry-run mode (no writes).
    """

    email: EmailConfig = field(default_factory=EmailConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    dry_run: bool = False


def _apply_env_overrides(config: AppConfig) -> None:
    """Overlay environment variables onto the config.

    Args:
        config: AppConfig instance to mutate in-place.
    """
    env_map: list[tuple[str, object, str]] = [
        ("EMAIL_ADDRESS", config.email, "address"),
        ("EMAIL_PASSWORD", config.email, "password"),
        ("IMAP_HOST", config.email, "imap_host"),
        ("DB_HOST", config.database, "host"),
        ("DB_NAME", config.database, "name"),
        ("DB_USER", config.database, "user"),
        ("DB_PASSWORD", config.database, "password"),
        ("SLACK_WEBHOOK_URL", config.slack, "webhook_url"),
        ("AWS_ACCESS_KEY_ID", config.storage, "access_key_id"),
        ("AWS_SECRET_ACCESS_KEY", config.storage, "secret_access_key"),
    ]
    for env_var, obj, attr in env_map:
        value = os.environ.get(env_var)
        if value is not None:
            setattr(obj, attr, value)


def _dict_to_config(data: dict) -> AppConfig:
    """Convert a nested dict (from YAML) to an AppConfig.

    Args:
        data: Dictionary parsed from YAML config file.

    Returns:
        Populated AppConfig instance.
    """
    config = AppConfig()
    section_map: dict[str, object] = {
        "email": config.email,
        "database": config.database,
        "slack": config.slack,
        "retry": config.retry,
        "metrics": config.metrics,
        "storage": config.storage,
        "validation": config.validation,
        "logging": config.logging,
    }

    for section_name, section_obj in section_map.items():
        section_data = data.get(section_name, {})
        if isinstance(section_data, dict):
            for key, value in section_data.items():
                if hasattr(section_obj, key):
                    setattr(section_obj, key, value)

    if "dry_run" in data:
        config.dry_run = data["dry_run"]

    return config


def load_config(config_path: str = "config/config.yaml") -> AppConfig:
    """Load application configuration from YAML file with env var overlays.

    Reads the YAML config file, then overlays any set environment variables
    on top (env vars take precedence for secrets).

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Fully populated AppConfig instance.
    """
    load_dotenv()

    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file, "r") as f:
            data = yaml.safe_load(f) or {}
        config = _dict_to_config(data)
    else:
        config = AppConfig()

    _apply_env_overrides(config)
    return config
