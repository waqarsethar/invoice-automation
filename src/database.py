"""Database loader for storing invoices using SQLAlchemy Core."""

import logging
from datetime import datetime, timezone
from typing import Self

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
)
from sqlalchemy.engine import Engine

from src.config_loader import DatabaseConfig
from src.exceptions import DatabaseError
from src.models import InvoiceData, ProcessingStatus

logger = logging.getLogger("invoice_automation.db_loader")

metadata = MetaData()

invoices_table = Table(
    "invoices",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("invoice_number", String(64), nullable=False, unique=True),
    Column("vendor_name", String(256), nullable=False),
    Column("invoice_date", DateTime, nullable=False),
    Column("due_date", DateTime, nullable=True),
    Column("total_amount", Numeric(15, 2), nullable=False),
    Column("currency", String(3), nullable=False, default="USD"),
    Column("po_number", String(64), nullable=True),
    Column("status", String(32), nullable=False),
    Column("raw_text", Text, nullable=True),
    Column("email_from", String(256), nullable=True),
    Column("email_subject", String(512), nullable=True),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

audit_log_table = Table(
    "invoice_audit_log",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("invoice_number", String(64), nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("event_data", Text, nullable=True),
    Column("created_at", DateTime, nullable=False),
)


class DatabaseLoader:
    """Manages database operations for invoice storage.

    Use as a context manager for automatic connection management.

    Args:
        config: Database connection configuration.
    """

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._engine: Engine | None = None

    def __enter__(self) -> Self:
        """Create database engine and connect."""
        self.connect()
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> bool:
        """Dispose of the database engine."""
        self.disconnect()
        return False

    def connect(self) -> None:
        """Create the SQLAlchemy engine.

        Raises:
            DatabaseError: If engine creation fails.
        """
        try:
            logger.info("Connecting to database at %s", self._config.host)
            self._engine = create_engine(
                self._config.url,
                pool_pre_ping=True,
                pool_size=5,
            )
            logger.info("Database engine created successfully")
        except Exception as exc:
            raise DatabaseError(
                message=f"Failed to create database engine: {exc}",
                details={"host": self._config.host, "database": self._config.name},
            ) from exc

    def disconnect(self) -> None:
        """Dispose of the database engine."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            logger.info("Database engine disposed")

    def create_tables(self) -> None:
        """Create all tables if they don't exist.

        Raises:
            DatabaseError: If table creation fails.
        """
        if self._engine is None:
            raise DatabaseError(message="Not connected to database")

        try:
            metadata.create_all(self._engine)
            logger.info("Database tables created/verified")
        except Exception as exc:
            raise DatabaseError(
                message=f"Failed to create tables: {exc}",
            ) from exc

    def check_duplicate(self, invoice_number: str) -> bool:
        """Check if an invoice with the given number already exists.

        Args:
            invoice_number: Invoice number to check.

        Returns:
            True if a duplicate exists, False otherwise.

        Raises:
            DatabaseError: If the query fails.
        """
        if self._engine is None:
            raise DatabaseError(message="Not connected to database")

        try:
            with self._engine.connect() as conn:
                stmt = select(invoices_table.c.id).where(
                    invoices_table.c.invoice_number == invoice_number
                )
                result = conn.execute(stmt)
                return result.fetchone() is not None
        except Exception as exc:
            raise DatabaseError(
                message=f"Failed to check for duplicate: {exc}",
                details={"invoice_number": invoice_number},
            ) from exc

    def insert_invoice(
        self,
        invoice: InvoiceData,
        email_from: str = "",
        email_subject: str = "",
    ) -> str:
        """Insert an invoice record in a transaction.

        Args:
            invoice: Parsed invoice data.
            email_from: Source email address.
            email_subject: Source email subject.

        Returns:
            The generated record ID.

        Raises:
            DatabaseError: If the insert fails.
        """
        if self._engine is None:
            raise DatabaseError(message="Not connected to database")

        import uuid

        record_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        try:
            with self._engine.begin() as conn:
                conn.execute(
                    insert(invoices_table).values(
                        id=record_id,
                        invoice_number=invoice.invoice_number,
                        vendor_name=invoice.vendor_name,
                        invoice_date=datetime.combine(
                            invoice.invoice_date, datetime.min.time()
                        ),
                        due_date=(
                            datetime.combine(invoice.due_date, datetime.min.time())
                            if invoice.due_date
                            else None
                        ),
                        total_amount=float(invoice.total_amount),
                        currency=invoice.currency,
                        po_number=invoice.po_number,
                        status=ProcessingStatus.STORED.value,
                        raw_text=invoice.raw_text,
                        email_from=email_from,
                        email_subject=email_subject,
                        created_at=now,
                        updated_at=now,
                    )
                )

                # Record audit event
                self._insert_audit_event(
                    conn,
                    invoice_number=invoice.invoice_number,
                    event_type="invoice_stored",
                    event_data=f"Stored invoice from {invoice.vendor_name}, amount: {invoice.total_amount}",
                )

            logger.info(
                "Inserted invoice %s (ID: %s)",
                invoice.invoice_number,
                record_id,
            )
            return record_id

        except Exception as exc:
            raise DatabaseError(
                message=f"Failed to insert invoice: {exc}",
                details={"invoice_number": invoice.invoice_number},
            ) from exc

    def record_audit_event(
        self,
        invoice_number: str,
        event_type: str,
        event_data: str = "",
    ) -> None:
        """Record an audit log entry.

        Args:
            invoice_number: Associated invoice number.
            event_type: Type of event (e.g., 'validation_failed').
            event_data: Additional event details.

        Raises:
            DatabaseError: If the insert fails.
        """
        if self._engine is None:
            raise DatabaseError(message="Not connected to database")

        try:
            with self._engine.begin() as conn:
                self._insert_audit_event(
                    conn, invoice_number, event_type, event_data
                )
        except Exception as exc:
            raise DatabaseError(
                message=f"Failed to record audit event: {exc}",
                details={
                    "invoice_number": invoice_number,
                    "event_type": event_type,
                },
            ) from exc

    def _insert_audit_event(
        self,
        conn: object,
        invoice_number: str,
        event_type: str,
        event_data: str,
    ) -> None:
        """Insert an audit log record within an existing connection.

        Args:
            conn: Active SQLAlchemy connection.
            invoice_number: Associated invoice number.
            event_type: Type of event.
            event_data: Additional details.
        """
        import uuid

        conn.execute(  # type: ignore[union-attr]
            insert(audit_log_table).values(
                id=str(uuid.uuid4()),
                invoice_number=invoice_number,
                event_type=event_type,
                event_data=event_data,
                created_at=datetime.now(timezone.utc),
            )
        )
