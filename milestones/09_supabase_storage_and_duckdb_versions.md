# Milestone 9: Supabase Storage + DuckDB Dataset Versions

## Goal

Move persistent dataset artifacts out of local storage and into Supabase Storage, while representing each materialized `DatasetVersion` as a `.duckdb` file.

Supabase Postgres remains the metadata/control database.

Supabase Storage stores:

* raw uploads
* `.duckdb` dataset version files
* generated result artifacts, if needed later

No background worker in M9. No job table. No queue. No frontend work. No saved views. No saved visuals. No chat.

Temporary local files are allowed only as scratch files while creating or reading `.duckdb` artifacts.

---

## Architecture Rules

Use this split:

* Supabase Postgres stores metadata, lineage, plans, decisions, and result records.
* Supabase Storage stores persistent files.
* DuckDB runs inside backend services using temporary local files only.
* Do not store raw uploads or `.duckdb` binary files in Postgres.
* Do not store persistent dataset files on local disk.
* Temporary local files must be deleted after success or failure.

Dataset version rule:

* A `DatasetVersion` is a materialized state of a dataset.
* Each materialized `DatasetVersion` should point to one `.duckdb` artifact in storage.
* A `.duckdb` version file may contain many tables.
* Existing dataset version files are immutable.
* Cleaning and feature execution create new `.duckdb` version files.
* Visualization reads from an existing `.duckdb` version and does not mutate it.

Storage path convention:

* Raw uploads:

  `workspaces/{workspace_id}/datasets/{dataset_id}/raw_uploads/{uploaded_file_id}_{filename}`

* Dataset versions:

  `workspaces/{workspace_id}/datasets/{dataset_id}/versions/v{version_number}_{version_type}.duckdb`

* Result artifacts:

  `workspaces/{workspace_id}/datasets/{dataset_id}/results/{artifact_id}.{ext}`

Future result artifact examples:

* saved view export:

  `workspaces/{workspace_id}/datasets/{dataset_id}/results/{saved_view_id}.csv`

* saved visual data:

  `workspaces/{workspace_id}/datasets/{dataset_id}/results/{visual_id}.json`

Postgres should store storage metadata such as:

* storage_backend
* storage_bucket
* storage_path
* storage_format
* row_count
* column_count

Do not implement saved view or saved visual models/routes in M9. That belongs to M11.

---

## M9A: Storage Abstraction + Supabase Storage Backend

Implement a storage abstraction for persistent files.

Required interface should support:

* save bytes/file
* read/download bytes/file
* delete file
* check existence if useful
* return storage metadata/path

Implement:

* local storage backend for tests/dev
* Supabase Storage backend for production/configured environments

Configuration should support:

* storage backend: local or supabase
* Supabase URL
* Supabase service role key
* Supabase storage bucket name
* temp directory for scratch files

Rules:

* Do not store persistent uploaded or derived files on local disk when Supabase backend is selected.
* Do not store file bytes in Postgres.
* Keep existing tests working with local storage backend.
* Add tests with mocked/fake storage where external Supabase calls would otherwise be required.
* Do not add Supabase Auth.
* Do not change analytics business logic.

Acceptance criteria:

* storage service can save/read/delete files
* local backend works in tests
* Supabase backend is implemented behind the same interface
* config chooses backend
* README explains required Supabase env variables
* tests do not require live Supabase credentials

---

## M9B: DuckDB Version Artifact Utilities

Implement DuckDB utilities for dataset version files.

Required utilities:

* create a `.duckdb` file from uploaded CSV/Excel tables
* list tables in a `.duckdb` file
* read limited table preview from a `.duckdb` file
* get table row/column counts
* copy existing version into a new version file if useful
* export/import through temporary local scratch files

CSV behavior:

* one CSV file becomes one table
* table name should be derived from the file name and sanitized

Excel behavior:

* each sheet becomes one table
* table names should be derived from sheet names and sanitized
* empty sheets should be skipped or handled safely

Table naming rules:

* sanitize unsafe names
* avoid SQL injection through table names
* preserve a user-facing logical name separately if needed
* ensure duplicate names are disambiguated

Rules:

* One `.duckdb` file represents one materialized `DatasetVersion`.
* A `.duckdb` file may contain many tables.
* Existing version files are immutable.
* Do not mutate an existing version file in place.
* Download from storage to temp path, process with DuckDB, upload result, then clean temp files.
* Do not add background jobs in M9.
* Do not add frontend work.

Acceptance criteria:

* CSV upload can become a DuckDB version file
* Excel upload with multiple sheets can become a DuckDB version file with multiple tables
* table names are sanitized safely
* table metadata can be extracted from the DuckDB file
* limited preview works
* temp files are cleaned after success/failure
* tests use temporary files and fake/local storage

---

## M9C: Integrate Upload/Profile/Existing Services with DuckDB Version Storage

Integrate existing dataset flows with DuckDB version artifacts.

Upload/import behavior:

* save raw upload to storage
* create an original `.duckdb` version artifact
* upload `.duckdb` artifact to storage
* create/update `DatasetVersion` metadata with storage fields
* create/update `DatasetTable` metadata from actual DuckDB tables

Profile behavior:

* read selected `DatasetVersion` from its `.duckdb` artifact
* profile all relevant tables from that version
* do not assume one dataset equals one file
* do not assume one dataset version equals one table

Cleaning/feature/visualization compatibility:

* existing services should be able to locate tables from `DatasetVersion.storage_path`
* if full migration is too broad, add compatibility helpers and migrate only the smallest necessary paths
* cleaning should still create a new `DatasetVersion`
* feature execution should still create a new `DatasetVersion`
* visualization should read from the selected `DatasetVersion` and not mutate it

Rules:

* Do not create a new `Dataset` when uploading a file to an existing dataset.
* Do not store persistent files locally.
* Do not store DuckDB binary content in Postgres.
* Do not add job/worker logic.
* Do not add frontend work.
* Do not rewrite business logic broadly.

Acceptance criteria:

* upload creates raw file record and original DuckDB-backed `DatasetVersion`
* `DatasetVersion` has storage metadata for `.duckdb`
* `DatasetTable` rows match actual DuckDB tables
* profiling works from DuckDB-backed versions
* previous version semantics remain intact
* existing visualization flow can read from the current version or has a clear compatibility adapter
* tests cover multi-table dataset versions

---

## M9D: Documentation, Migration Cleanup, and Tests

Finalize documentation and compatibility.

Update README with:

* Supabase Postgres connection setup
* Supabase Storage bucket setup
* required env variables
* local dev storage mode
* note that local files are temporary scratch only in Supabase mode
* note that persistent raw uploads and `.duckdb` files live in Supabase Storage when Supabase backend is selected

Required env variables should include, if applicable:

* `DATABASE_URL`
* `STORAGE_BACKEND`
* `SUPABASE_URL`
* `SUPABASE_SERVICE_ROLE_KEY`
* `SUPABASE_STORAGE_BUCKET`
* `TEMP_DIR`

Add/adjust tests for:

* storage backend selection
* local/fake storage save/read/delete
* raw upload path generation
* result artifact path generation
* DuckDB version artifact creation
* multiple-table Excel import
* DatasetVersion storage metadata
* DatasetTable metadata extraction
* profiling from DuckDB-backed version
* no persistent local storage in Supabase mode where testable

Do not add:

* workers
* queues
* job table
* frontend redesign
* saved views backend
* saved visuals backend
* dataset chat backend
* Supabase Auth
* LLM calls

Acceptance criteria:

* M9 tests pass
* existing relevant upload/profile/visualization tests pass or are updated for DuckDB-backed versions
* README documents Supabase setup clearly
* local test mode still works without live Supabase credentials
