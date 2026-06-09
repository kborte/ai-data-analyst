"""add jobs table

Revision ID: c7e2f3a4b5d6
Revises: b3f1c2d4e5a6
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c7e2f3a4b5d6"
down_revision = "b3f1c2d4e5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.workspace_id"), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.dataset_id"), nullable=True),
        sa.Column("input_dataset_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dataset_versions.dataset_version_id"), nullable=True),
        sa.Column("job_type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="queued"),
        sa.Column("payload_json", postgresql.JSONB, nullable=True),
        sa.Column("result_type", sa.Text, nullable=True),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("output_dataset_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dataset_versions.dataset_version_id"), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("progress_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_jobs_dataset_id", "jobs", ["dataset_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_workspace_id", "jobs", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_workspace_id", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_dataset_id", table_name="jobs")
    op.drop_table("jobs")
