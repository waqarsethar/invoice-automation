"""Tests for the database loader component."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.config_loader import DatabaseConfig
from src.database import DatabaseLoader
from src.exceptions import DatabaseError
from src.models import InvoiceData


@pytest.fixture
def db_config() -> DatabaseConfig:
    """Test database configuration."""
    return DatabaseConfig(
        host="localhost",
        port=5432,
        name="test_db",
        user="test_user",
        password="test_pass",
    )


@pytest.fixture
def sample_invoice() -> InvoiceData:
    """Sample invoice data for database tests."""
    return InvoiceData(
        invoice_number="INV-2024-001",
        vendor_name="Acme Corp",
        invoice_date=date(2024, 1, 15),
        due_date=date(2024, 2, 15),
        total_amount=Decimal("500.00"),
        currency="USD",
        po_number="PO-2024-100",
        raw_text="sample text",
    )


class TestDatabaseLoaderConnect:
    """Tests for connection management."""

    @patch("src.database.create_engine")
    def test_connect_creates_engine(
        self, mock_create_engine: MagicMock, db_config: DatabaseConfig
    ) -> None:
        """Connect creates a SQLAlchemy engine."""
        loader = DatabaseLoader(db_config)
        loader.connect()

        mock_create_engine.assert_called_once_with(
            db_config.url,
            pool_pre_ping=True,
            pool_size=5,
        )

    @patch("src.database.create_engine")
    def test_connect_failure_raises(
        self, mock_create_engine: MagicMock, db_config: DatabaseConfig
    ) -> None:
        """Connection failure raises DatabaseError."""
        mock_create_engine.side_effect = Exception("Connection refused")
        loader = DatabaseLoader(db_config)

        with pytest.raises(DatabaseError, match="Failed to create"):
            loader.connect()

    @patch("src.database.create_engine")
    def test_context_manager(
        self, mock_create_engine: MagicMock, db_config: DatabaseConfig
    ) -> None:
        """Context manager connects and disconnects."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        with DatabaseLoader(db_config):
            pass

        mock_engine.dispose.assert_called_once()

    def test_disconnect_without_connect(
        self, db_config: DatabaseConfig
    ) -> None:
        """Disconnecting without connecting is a no-op."""
        loader = DatabaseLoader(db_config)
        loader.disconnect()  # Should not raise


class TestDatabaseLoaderOperations:
    """Tests for database operations."""

    def test_insert_without_connection_raises(
        self, db_config: DatabaseConfig, sample_invoice: InvoiceData
    ) -> None:
        """Insert without connection raises DatabaseError."""
        loader = DatabaseLoader(db_config)
        with pytest.raises(DatabaseError, match="Not connected"):
            loader.insert_invoice(sample_invoice)

    def test_check_duplicate_without_connection_raises(
        self, db_config: DatabaseConfig
    ) -> None:
        """Duplicate check without connection raises DatabaseError."""
        loader = DatabaseLoader(db_config)
        with pytest.raises(DatabaseError, match="Not connected"):
            loader.check_duplicate("INV-001")

    @patch("src.database.create_engine")
    def test_check_duplicate_returns_false(
        self, mock_create_engine: MagicMock, db_config: DatabaseConfig
    ) -> None:
        """Returns False when no duplicate exists."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(
            return_value=mock_conn
        )
        mock_engine.connect.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_conn.execute.return_value = mock_result

        loader = DatabaseLoader(db_config)
        loader.connect()
        assert loader.check_duplicate("INV-NEW") is False

    @patch("src.database.create_engine")
    def test_check_duplicate_returns_true(
        self, mock_create_engine: MagicMock, db_config: DatabaseConfig
    ) -> None:
        """Returns True when duplicate exists."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(
            return_value=mock_conn
        )
        mock_engine.connect.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("some-id",)
        mock_conn.execute.return_value = mock_result

        loader = DatabaseLoader(db_config)
        loader.connect()
        assert loader.check_duplicate("INV-EXISTS") is True

    @patch("src.database.create_engine")
    def test_insert_invoice_success(
        self,
        mock_create_engine: MagicMock,
        db_config: DatabaseConfig,
        sample_invoice: InvoiceData,
    ) -> None:
        """Successfully inserts an invoice."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__ = MagicMock(
            return_value=mock_conn
        )
        mock_engine.begin.return_value.__exit__ = MagicMock(
            return_value=False
        )

        loader = DatabaseLoader(db_config)
        loader.connect()
        record_id = loader.insert_invoice(
            sample_invoice,
            email_from="test@test.com",
            email_subject="Invoice",
        )

        assert record_id is not None
        assert isinstance(record_id, str)
        # Should have called execute twice: invoice + audit log
        assert mock_conn.execute.call_count == 2

    def test_create_tables_without_connection_raises(
        self, db_config: DatabaseConfig
    ) -> None:
        """Create tables without connection raises DatabaseError."""
        loader = DatabaseLoader(db_config)
        with pytest.raises(DatabaseError, match="Not connected"):
            loader.create_tables()

    def test_record_audit_without_connection_raises(
        self, db_config: DatabaseConfig
    ) -> None:
        """Record audit without connection raises DatabaseError."""
        loader = DatabaseLoader(db_config)
        with pytest.raises(DatabaseError, match="Not connected"):
            loader.record_audit_event("INV-001", "test_event")
