"""add saved_views table

Revision ID: d1e3f4a5b6c7
Revises: c7e2f3a4b5d6
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d1e3f4a5b6c7"
down_revision = "c7e2f3a4b5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_views",
        sa.Column("saved_view_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.workspace_id"), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.dataset_id"), nullable=False),
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dataset_versions.dataset_version_id"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source_type", sa.Text, nullable=False),
        sa.Column("source_spec_json", postgresql.JSONB, nullable=True),
        sa.Column("storage_backend", sa.Text, nullable=True),
        sa.Column("storage_bucket", sa.Text, nullable=True),
        sa.Column("storage_path", sa.Text, nullable=True),
        sa.Column("storage_format", sa.Text, nullable=True),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("column_count", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_saved_views_dataset_version_id", "saved_views", ["dataset_version_id"])
    op.create_index("ix_saved_views_dataset_id", "saved_views", ["dataset_id"])
    op.create_index("ix_saved_views_workspace_id", "saved_views", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_views_workspace_id", table_name="saved_views")
    op.drop_index("ix_saved_views_dataset_id", table_name="saved_views")
    op.drop_index("ix_saved_views_dataset_version_id", table_name="saved_views")
    op.drop_table("saved_views")
