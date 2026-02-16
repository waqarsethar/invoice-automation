-- Database initialization script for the invoice automation system.
-- Creates tables if they don't already exist.

CREATE TABLE IF NOT EXISTS invoices (
    id              VARCHAR(64)     PRIMARY KEY,
    invoice_number  VARCHAR(64)     NOT NULL UNIQUE,
    vendor_name     VARCHAR(256)    NOT NULL,
    invoice_date    TIMESTAMP       NOT NULL,
    due_date        TIMESTAMP,
    total_amount    NUMERIC(15, 2)  NOT NULL,
    currency        VARCHAR(3)      NOT NULL DEFAULT 'USD',
    po_number       VARCHAR(64),
    status          VARCHAR(32)     NOT NULL,
    raw_text        TEXT,
    email_from      VARCHAR(256),
    email_subject   VARCHAR(512),
    created_at      TIMESTAMP       NOT NULL,
    updated_at      TIMESTAMP       NOT NULL
);

CREATE TABLE IF NOT EXISTS invoice_audit_log (
    id              VARCHAR(64)     PRIMARY KEY,
    invoice_number  VARCHAR(64)     NOT NULL,
    event_type      VARCHAR(64)     NOT NULL,
    event_data      TEXT,
    created_at      TIMESTAMP       NOT NULL
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_invoices_invoice_number ON invoices (invoice_number);
CREATE INDEX IF NOT EXISTS idx_invoices_vendor_name ON invoices (vendor_name);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices (status);
CREATE INDEX IF NOT EXISTS idx_invoices_created_at ON invoices (created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_invoice_number ON invoice_audit_log (invoice_number);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON invoice_audit_log (created_at);
