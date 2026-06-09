"""add visualization plan and result tables

Revision ID: b3f1c2d4e5a6
Revises: da909bd26a67
Create Date: 2026-06-09

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "b3f1c2d4e5a6"
down_revision = "da909bd26a67"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visualization_plans",
        sa.Column("visualization_plan_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_version_id", UUID(as_uuid=True), sa.ForeignKey("dataset_versions.dataset_version_id"), nullable=False),
        sa.Column("analysis_run_id", UUID(as_uuid=True)),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("plan_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "visualization_results",
        sa.Column("visualization_result_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("visualization_plan_id", UUID(as_uuid=True), sa.ForeignKey("visualization_plans.visualization_plan_id"), nullable=False),
        sa.Column("dataset_version_id", UUID(as_uuid=True), sa.ForeignKey("dataset_versions.dataset_version_id"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("result_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("visualization_results")
    op.drop_table("visualization_plans")
