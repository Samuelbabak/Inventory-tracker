"""devices qr and reconciliation

Revision ID: 59c93f9d8ad4
Revises: acd800719a81
Create Date: 2026-09-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "59c93f9d8ad4"
down_revision: str | None = "acd800719a81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USER_FK = "users.id"
_WAREHOUSE_FK = "warehouses.id"


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("device_identifier", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("enrolled_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["enrolled_by_user_id"],
            [_USER_FK],
            name=op.f("fk_devices_enrolled_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            [_WAREHOUSE_FK],
            name=op.f("fk_devices_warehouse_id_warehouses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_devices")),
        sa.UniqueConstraint(
            "warehouse_id",
            "device_identifier",
            name=op.f("uq_devices_warehouse_id"),
        ),
    )
    op.create_index(op.f("ix_devices_warehouse_id"), "devices", ["warehouse_id"])
    op.create_table(
        "qr_tokens",
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            [_USER_FK],
            name=op.f("fk_qr_tokens_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            [_WAREHOUSE_FK],
            name=op.f("fk_qr_tokens_warehouse_id_warehouses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qr_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_qr_tokens_token_hash")),
    )
    op.create_index(op.f("ix_qr_tokens_target_id"), "qr_tokens", ["target_id"])
    op.create_index(op.f("ix_qr_tokens_target_type"), "qr_tokens", ["target_type"])
    op.create_index(op.f("ix_qr_tokens_warehouse_id"), "qr_tokens", ["warehouse_id"])
    op.create_table(
        "reconciliation_runs",
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("initiated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("checked_count", sa.Integer(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("difference_count", sa.Integer(), nullable=False),
        sa.Column("differences", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"],
            [_USER_FK],
            name=op.f("fk_reconciliation_runs_initiated_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            [_WAREHOUSE_FK],
            name=op.f("fk_reconciliation_runs_warehouse_id_warehouses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reconciliation_runs")),
    )
    op.create_index(
        op.f("ix_reconciliation_runs_warehouse_id"),
        "reconciliation_runs",
        ["warehouse_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_reconciliation_runs_warehouse_id"), table_name="reconciliation_runs")
    op.drop_table("reconciliation_runs")
    op.drop_index(op.f("ix_qr_tokens_warehouse_id"), table_name="qr_tokens")
    op.drop_index(op.f("ix_qr_tokens_target_type"), table_name="qr_tokens")
    op.drop_index(op.f("ix_qr_tokens_target_id"), table_name="qr_tokens")
    op.drop_table("qr_tokens")
    op.drop_index(op.f("ix_devices_warehouse_id"), table_name="devices")
    op.drop_table("devices")