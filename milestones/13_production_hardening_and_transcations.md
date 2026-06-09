# Milestone 13: Production Hardening + Transactions

## Goal

Make the MVP safer and more reliable without adding new product features.

This milestone focuses on:

* transaction boundaries around high-risk multi-table metadata writes
* basic Supabase Storage + Postgres consistency handling
* clearer errors for common local failure cases
* final documentation and focused tests

## Non-goals

Do not implement:

* dataset events
* conversation persistence
* history timeline
* frontend work
* new analytics tools
* new cleaning logic
* new feature engineering logic
* dashboard builder
* cleanup daemon
* broad repository rewrites
* full observability infrastructure

Dataset events and conversation persistence are deferred to a later optional milestone.

## Core Rule

If one logical operation writes to multiple Postgres tables, it should commit or fail as one unit.

## Storage Rule

Supabase Storage writes are outside Postgres transactions.

For M13:

* do not store file bytes or large result rows in Postgres
* keep large artifacts in storage
* if DB metadata write fails after storage upload, attempt best-effort cleanup only if simple
* if cleanup is not simple, document the limitation
* do not build a cleanup daemon

## M13A: Targeted Hardening Implementation

Implement targeted production hardening for the existing MVP.

Do the smallest safe implementation for:

* transaction boundaries around high-risk multi-table metadata writes
* basic Supabase Storage + Postgres consistency handling
* clearer errors for common local failure cases

Prioritize whichever of these flows exist in the current codebase:

* `DatasetVersion` plus `DatasetTable` creation
* upload/import metadata creation
* cleaning result plus cleaned `DatasetVersion` metadata
* feature result plus enriched `DatasetVersion` metadata
* `SavedView` creation
* `SavedVisual` creation
* analytics output save flow
* job completion paired with result metadata

Rules:

* services define transaction boundaries
* routes stay thin
* keep changes targeted
* preserve existing API behavior
* do not rewrite the persistence layer broadly
* do not pretend Supabase Storage writes are part of Postgres transactions
* if DB metadata write fails after storage upload, attempt best-effort cleanup only if simple
* if a flow is too risky to refactor safely, document it as a limitation

Acceptance criteria:

* highest-risk multi-table writes are transactional where feasible
* at least one rollback path is tested
* storage/DB consistency behavior is intentional and documented
* common local error cases return clearer errors
* no new product features are added

## M13B: Final Docs and Focused Tests

Add final documentation and focused tests for the hardening pass.

Tests should cover, where feasible:

* one transaction commit path
* one transaction rollback path
* one storage/DB consistency failure path if simple
* saved view creation still works
* saved visual creation still works
* analytics ask/save still works if relevant
* relevant upload/profile/cleaning/feature smoke tests

Documentation should explain:

* transaction boundaries for multi-table writes
* Supabase Storage writes are outside Postgres transactions
* large artifacts live in storage, not Postgres
* local temp files are scratch only
* known limitations
* dataset events and conversation persistence are deferred to a later optional milestone

Acceptance criteria:

* relevant tests pass
* docs match current architecture
* known limitations are explicit
* no new product features are introduced
