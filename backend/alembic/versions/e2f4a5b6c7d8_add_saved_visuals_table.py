"""add saved_visuals table

Revision ID: e2f4a5b6c7d8
Revises: d1e3f4a5b6c7
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e2f4a5b6c7d8"
down_revision = "d1e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_visuals",
        sa.Column("visual_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.workspace_id"), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.dataset_id"), nullable=False),
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dataset_versions.dataset_version_id"), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("chart_type", sa.Text, nullable=False),
        sa.Column("chart_spec_json", postgresql.JSONB, nullable=True),
        sa.Column("source_type", sa.Text, nullable=False),
        sa.Column("source_visualization_result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_view_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_spec_json", postgresql.JSONB, nullable=True),
        sa.Column("data_storage_backend", sa.Text, nullable=True),
        sa.Column("data_storage_bucket", sa.Text, nullable=True),
        sa.Column("data_storage_path", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_saved_visuals_dataset_version_id", "saved_visuals", ["dataset_version_id"])
    op.create_index("ix_saved_visuals_dataset_id", "saved_visuals", ["dataset_id"])
    op.create_index("ix_saved_visuals_workspace_id", "saved_visuals", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_visuals_workspace_id", table_name="saved_visuals")
    op.drop_index("ix_saved_visuals_dataset_id", table_name="saved_visuals")
    op.drop_index("ix_saved_visuals_dataset_version_id", table_name="saved_visuals")
    op.drop_table("saved_visuals")
