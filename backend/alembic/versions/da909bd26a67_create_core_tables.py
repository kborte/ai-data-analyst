"""create core tables

Revision ID: da909bd26a67
Revises:
Create Date: 2026-06-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "da909bd26a67"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "workspaces",
        sa.Column("workspace_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_by_user_id", UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "workspace_memberships",
        sa.Column("membership_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.workspace_id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text()),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "data_sources",
        sa.Column("data_source_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.workspace_id"), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("storage_path", sa.Text()),
        sa.Column("created_by_user_id", UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "uploaded_files",
        sa.Column("file_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True)),
        sa.Column("data_source_id", UUID(as_uuid=True), sa.ForeignKey("data_sources.data_source_id"), nullable=False),
        sa.Column("file_kind", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_user_id", UUID(as_uuid=True)),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "datasets",
        sa.Column("dataset_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_by_user_id", UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "dataset_sources",
        sa.Column("dataset_source_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.dataset_id"), nullable=False),
        sa.Column("data_source_id", UUID(as_uuid=True), sa.ForeignKey("data_sources.data_source_id"), nullable=False),
        sa.Column("source_role", sa.Text()),
    )

    op.create_table(
        "dataset_versions",
        sa.Column("dataset_version_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.dataset_id"), nullable=False),
        sa.Column("parent_version_id", UUID(as_uuid=True), sa.ForeignKey("dataset_versions.dataset_version_id")),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("version_type", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("storage_path", sa.Text()),
        sa.Column("row_count", sa.Integer()),
        sa.Column("column_count", sa.Integer()),
        sa.Column("created_by_user_id", UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", JSONB),
    )

    op.create_table(
        "dataset_tables",
        sa.Column("table_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_version_id", UUID(as_uuid=True), sa.ForeignKey("dataset_versions.dataset_version_id"), nullable=False),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text()),
        sa.Column("row_count", sa.Integer()),
        sa.Column("column_count", sa.Integer()),
    )

    op.create_table(
        "context_documents",
        sa.Column("context_document_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("data_source_id", UUID(as_uuid=True), sa.ForeignKey("data_sources.data_source_id")),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "data_profiles",
        sa.Column("profile_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_version_id", UUID(as_uuid=True), sa.ForeignKey("dataset_versions.dataset_version_id"), nullable=False),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("profile_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "cleaning_plans",
        sa.Column("cleaning_plan_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_version_id", UUID(as_uuid=True), sa.ForeignKey("dataset_versions.dataset_version_id"), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True)),
        sa.Column("dataset_id", UUID(as_uuid=True)),
        sa.Column("profile_id", UUID(as_uuid=True)),
        sa.Column("analysis_run_id", UUID(as_uuid=True)),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("plan_json", JSONB, nullable=False),
        sa.Column("created_by_user_id", UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "cleaning_decisions",
        sa.Column("cleaning_decisions_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cleaning_plan_id", UUID(as_uuid=True), sa.ForeignKey("cleaning_plans.cleaning_plan_id"), nullable=False),
        sa.Column("decided_by_user_id", UUID(as_uuid=True)),
        sa.Column("decisions_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "cleaning_results",
        sa.Column("cleaning_result_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cleaning_plan_id", UUID(as_uuid=True), sa.ForeignKey("cleaning_plans.cleaning_plan_id"), nullable=False),
        sa.Column("cleaning_decisions_id", UUID(as_uuid=True), sa.ForeignKey("cleaning_decisions.cleaning_decisions_id")),
        sa.Column("input_dataset_version_id", UUID(as_uuid=True), sa.ForeignKey("dataset_versions.dataset_version_id"), nullable=False),
        sa.Column("output_dataset_version_id", UUID(as_uuid=True), sa.ForeignKey("dataset_versions.dataset_version_id")),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("row_count_before", sa.Integer()),
        sa.Column("row_count_after", sa.Integer()),
        sa.Column("execution_log_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "feature_plans",
        sa.Column("feature_plan_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_version_id", UUID(as_uuid=True), sa.ForeignKey("dataset_versions.dataset_version_id"), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True)),
        sa.Column("dataset_id", UUID(as_uuid=True)),
        sa.Column("profile_id", UUID(as_uuid=True)),
        sa.Column("analysis_run_id", UUID(as_uuid=True)),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("plan_json", JSONB, nullable=False),
        sa.Column("created_by_user_id", UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "feature_decisions",
        sa.Column("feature_decisions_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("feature_plan_id", UUID(as_uuid=True), sa.ForeignKey("feature_plans.feature_plan_id"), nullable=False),
        sa.Column("decided_by_user_id", UUID(as_uuid=True)),
        sa.Column("decisions_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "feature_results",
        sa.Column("feature_result_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("feature_plan_id", UUID(as_uuid=True), sa.ForeignKey("feature_plans.feature_plan_id"), nullable=False),
        sa.Column("feature_decisions_id", UUID(as_uuid=True), sa.ForeignKey("feature_decisions.feature_decisions_id")),
        sa.Column("input_dataset_version_id", UUID(as_uuid=True), sa.ForeignKey("dataset_versions.dataset_version_id"), nullable=False),
        sa.Column("output_dataset_version_id", UUID(as_uuid=True), sa.ForeignKey("dataset_versions.dataset_version_id")),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("execution_status", sa.Text()),
        sa.Column("features_added", JSONB),
        sa.Column("execution_log_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("feature_results")
    op.drop_table("feature_decisions")
    op.drop_table("feature_plans")
    op.drop_table("cleaning_results")
    op.drop_table("cleaning_decisions")
    op.drop_table("cleaning_plans")
    op.drop_table("data_profiles")
    op.drop_table("context_documents")
    op.drop_table("dataset_tables")
    op.drop_table("dataset_versions")
    op.drop_table("dataset_sources")
    op.drop_table("datasets")
    op.drop_table("uploaded_files")
    op.drop_table("data_sources")
    op.drop_table("workspace_memberships")
    op.drop_table("workspaces")
    op.drop_table("users")
