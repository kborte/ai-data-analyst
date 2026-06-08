# Milestone 7: SQL Database Persistence

## Goal

Replace in-memory repositories with real SQL persistence.

Use PostgreSQL, SQLAlchemy, and Alembic.

Keep existing services and API behavior mostly unchanged.

No new analytics features. No LLM calls. No charts. No frontend redesign.

## Design rule

Services should not depend directly on SQLAlchemy sessions.

Services should call repositories.

Repositories should handle database reads/writes.

Keep this separation:

Route -> Service -> Repository -> Database

## Relational vs JSONB rule

Use PostgreSQL relational tables for top-level domain objects.

Use JSONB only for nested flexible artifacts.

Do not replace the database with JSON files.
Do not store every object as one giant JSON blob.
Do not normalize every nested cleaning/feature/profile step into separate tables yet.

Relational tables should exist for:

- workspaces
- workspace_memberships, if present
- data_sources
- uploaded_files
- datasets
- dataset_sources
- dataset_versions
- dataset_tables
- context_documents
- data_profiles
- cleaning_plans
- cleaning_decisions
- cleaning_results
- feature_plans
- feature_decisions
- feature_results

Use regular SQL columns for:

- IDs
- foreign keys
- status
- version numbers
- file/storage paths
- row_count
- column_count
- created_at
- created_by_user_id

Use JSONB columns for:

- profile_json
- plan_json
- decisions_json
- execution_log_json
- metadata

Examples:

`cleaning_plans` should be a SQL table with columns like:

- cleaning_plan_id UUID primary key
- workspace_id UUID foreign key
- dataset_id UUID foreign key
- dataset_version_id UUID foreign key
- profile_id UUID foreign key
- status text
- plan_json JSONB
- created_by_user_id UUID
- created_at timestamp

`feature_plans` should be a SQL table with columns like:

- feature_plan_id UUID primary key
- workspace_id UUID foreign key
- dataset_id UUID foreign key
- dataset_version_id UUID foreign key
- profile_id UUID foreign key
- status text
- plan_json JSONB
- created_by_user_id UUID
- created_at timestamp

The nested steps/features inside `plan_json` should not become separate SQL tables in M7.

## M7A: Database setup + ORM models

Set up:

- SQLAlchemy
- Alembic
- PostgreSQL config
- database session dependency
- ORM models for existing persisted objects


- DATABASE_URL
- TEST_DATABASE_URL if needed

Create ORM models for:

- users, if currently present
- workspaces
- workspace_memberships, if currently present
- data_sources
- uploaded_files
- datasets
- dataset_sources
- dataset_versions
- dataset_tables
- context_documents
- data_profiles
- cleaning_plans
- cleaning_decisions
- cleaning_results
- feature_plans
- feature_decisions
- feature_results

Use UUID primary keys.

Use JSON/JSONB columns for flexible artifacts:

- profile_json if needed
- plan_json
- decisions_json
- execution_log_json
- metadata

Do not normalize every nested cleaning/feature step into its own table yet.

Acceptance criteria:

- database config exists
- SQLAlchemy base/session setup exists
- Alembic initializes correctly
- first migration creates core tables
- app can start with database config

## M7B: Repository implementations

Implement database-backed repositories matching existing in-memory repository behavior.

Do not change service method signatures unless absolutely necessary.

Repositories should support existing operations for:

- save/get data sources
- save/get uploaded files
- save/get datasets
- save/get dataset versions
- save/get dataset tables
- save/get context documents
- save/get data profiles
- save/get cleaning plans/decisions/results
- save/get feature plans/decisions/results

Keep in-memory repositories only for tests if useful.

Acceptance criteria:

- services can use database repositories
- existing upload/profile/cleaning/feature flows still work
- no route should directly use SQLAlchemy
- no pandas logic in repositories

## M7C: Tests + migration cleanup

Add database/repository tests.

Use SQLite for quick repository tests only if compatible, or PostgreSQL test database if already easy.

Test:

- create dataset with source/version/tables
- save and retrieve data profile
- save and retrieve cleaning plan/decisions/result
- save and retrieve feature plan/decisions/result
- dataset version parent/child relationship works
- JSON fields round-trip correctly
- version numbers are preserved

Update README with:

- how to start database
- how to run migrations
- how to run backend with database
- how to reset local database

Acceptance criteria:

- migrations run
- repository tests pass
- backend starts
- existing API tests pass or are updated for DB-backed persistence