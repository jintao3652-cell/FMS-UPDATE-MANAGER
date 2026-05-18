"""baseline schema (1.0.6)

Captures the current full schema as of v1.0.6:
  users, login_audit, app_settings, email_log, email_verification_codes,
  crash_reports, email_outbox, invite_codes, cycle_subscriptions,
  cycle_notification_state, password_reset_codes.

On an empty DB this creates everything. On an existing DB that pre-dates
alembic, run `alembic stamp head` once so alembic believes this baseline
is already applied; future migrations then go through `alembic upgrade`.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    def has(name: str) -> bool:
        return name in existing

    if not has("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(64), nullable=False, unique=True, index=True),
            sa.Column("email", sa.String(255), nullable=True, unique=True, index=True),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("role", sa.String(32), nullable=False, server_default="user"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if not has("login_audit"):
        op.create_table(
            "login_audit",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(64), nullable=False),
            sa.Column("ip", sa.String(64), nullable=False, server_default=""),
            sa.Column("user_agent", sa.Text(), nullable=False),
            sa.Column("success", sa.Boolean(), nullable=False),
            sa.Column("detail", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if not has("app_settings"):
        op.create_table(
            "app_settings",
            sa.Column("key", sa.String(64), primary_key=True),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False,
                      server_default=sa.text("CURRENT_TIMESTAMP"),
                      onupdate=sa.text("CURRENT_TIMESTAMP")),
        )

    if not has("email_log"):
        op.create_table(
            "email_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("recipient", sa.String(255), nullable=False),
            sa.Column("subject", sa.String(255), nullable=False, server_default=""),
            sa.Column("purpose", sa.String(64), nullable=False, server_default=""),
            sa.Column("success", sa.Boolean(), nullable=False),
            sa.Column("error", sa.Text(), nullable=False),
            sa.Column("sent_by", sa.String(64), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if not has("email_verification_codes"):
        op.create_table(
            "email_verification_codes",
            sa.Column("email", sa.String(255), primary_key=True),
            sa.Column("code_hash", sa.String(128), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sent_ip", sa.String(64), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False,
                      server_default=sa.text("CURRENT_TIMESTAMP"),
                      onupdate=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("used_at", sa.DateTime(), nullable=True),
        )

    if not has("admin_audit"):
        op.create_table(
            "admin_audit",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("admin_username", sa.String(64), nullable=False),
            sa.Column("action", sa.String(64), nullable=False),
            sa.Column("target", sa.String(255), nullable=False, server_default=""),
            sa.Column("detail", sa.Text(), nullable=False),
            sa.Column("ip", sa.String(64), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if not has("crash_reports"):
        op.create_table(
            "crash_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("install_id", sa.String(64), nullable=False, server_default="", index=True),
            sa.Column("app", sa.String(64), nullable=False, server_default=""),
            sa.Column("version", sa.String(32), nullable=False, server_default="", index=True),
            sa.Column("kind", sa.String(32), nullable=False, server_default="", index=True),
            sa.Column("exc_type", sa.String(128), nullable=False, server_default="", index=True),
            sa.Column("exc_msg", sa.Text(), nullable=False),
            sa.Column("traceback", sa.Text(), nullable=False),
            sa.Column("platform", sa.String(255), nullable=False, server_default=""),
            sa.Column("python", sa.String(32), nullable=False, server_default=""),
            sa.Column("extra", sa.Text(), nullable=False),
            sa.Column("client_ts", sa.String(64), nullable=False, server_default=""),
            sa.Column("ip", sa.String(64), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), index=True),
        )

    if not has("email_outbox"):
        op.create_table(
            "email_outbox",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("recipient", sa.String(255), nullable=False),
            sa.Column("subject", sa.String(255), nullable=False, server_default=""),
            sa.Column("purpose", sa.String(64), nullable=False, server_default="", index=True),
            sa.Column("body_text", sa.Text(), nullable=False),
            sa.Column("body_html", sa.Text(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending", index=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("next_attempt_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), index=True),
            sa.Column("last_error", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
        )

    if not has("invite_codes"):
        op.create_table(
            "invite_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(64), nullable=False, unique=True, index=True),
            sa.Column("note", sa.String(255), nullable=False, server_default=""),
            sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if not has("cycle_subscriptions"):
        op.create_table(
            "cycle_subscriptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False, unique=True, index=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("last_notified_cycle", sa.String(16), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False,
                      server_default=sa.text("CURRENT_TIMESTAMP"),
                      onupdate=sa.text("CURRENT_TIMESTAMP")),
        )

    if not has("cycle_notification_state"):
        op.create_table(
            "cycle_notification_state",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("last_seen_cycle", sa.String(16), nullable=False, server_default=""),
            sa.Column("last_checked_at", sa.DateTime(), nullable=False,
                      server_default=sa.text("CURRENT_TIMESTAMP"),
                      onupdate=sa.text("CURRENT_TIMESTAMP")),
        )

    if not has("password_reset_codes"):
        op.create_table(
            "password_reset_codes",
            sa.Column("email", sa.String(255), primary_key=True),
            sa.Column("code_hash", sa.String(128), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sent_ip", sa.String(64), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False,
                      server_default=sa.text("CURRENT_TIMESTAMP"),
                      onupdate=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("used_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    # Baseline; we don't support downgrading below this.
    raise RuntimeError("cannot downgrade past baseline")
