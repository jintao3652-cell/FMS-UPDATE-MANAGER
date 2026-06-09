"""add composite indexes for hot worker / dashboard queries

- email_outbox: (status, next_attempt_at) for the SMTP retry worker poll.
- crash_reports: (version, created_at) and (exc_type, created_at) for the
  admin panel's version+date filters.
- login_audit: (created_at) for "today login" dashboard counters.

Revision ID: 0002_indexes
Revises: 0001_baseline
Create Date: 2026-05-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_indexes"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_index(insp, table: str, name: str) -> bool:
    try:
        return any(ix.get("name") == name for ix in insp.get_indexes(table))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not _has_index(insp, "email_outbox", "ix_email_outbox_status_next"):
        op.create_index(
            "ix_email_outbox_status_next",
            "email_outbox",
            ["status", "next_attempt_at"],
        )

    if not _has_index(insp, "crash_reports", "ix_crash_reports_version_created"):
        op.create_index(
            "ix_crash_reports_version_created",
            "crash_reports",
            ["version", "created_at"],
        )

    if not _has_index(insp, "crash_reports", "ix_crash_reports_exc_created"):
        op.create_index(
            "ix_crash_reports_exc_created",
            "crash_reports",
            ["exc_type", "created_at"],
        )

    if not _has_index(insp, "login_audit", "ix_login_audit_created_at"):
        op.create_index(
            "ix_login_audit_created_at",
            "login_audit",
            ["created_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_login_audit_created_at", table_name="login_audit")
    op.drop_index("ix_crash_reports_exc_created", table_name="crash_reports")
    op.drop_index("ix_crash_reports_version_created", table_name="crash_reports")
    op.drop_index("ix_email_outbox_status_next", table_name="email_outbox")
