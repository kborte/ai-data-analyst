# Milestone 2: File Upload and Source/Dataset Creation

## Goal

Implement local upload support for:

* CSV files
* Excel files
* text/markdown context files

The system should create the correct domain objects:

* DataSource
* UploadedFile
* Dataset
* DatasetSource
* DatasetVersion
* DatasetTable
* ContextDocument

Do not implement profiling, cleaning, feature engineering, visualization, LLM calls, database persistence, authentication, or external integrations.

## Scope

Build a minimal but reusable upload pipeline using local filesystem storage and in-memory repositories.

This milestone should answer:

> Can a user upload a CSV/Excel/text file, have it saved locally, and receive structured metadata plus preview data?

## Architecture rules

Follow `CLAUDE.md`.

Important:

* Keep routes thin.
* Put upload orchestration in services.
* Put file parsing/loading in tools.
* Put persistence behind repositories.
* Preserve original uploaded files.
* Do not overwrite files.
* Do not store raw file contents in schemas.
* Use local storage under `backend/storage/uploads`.
* Use existing Pydantic schemas from Milestone 1.
* Add new schemas only if necessary.
* Keep implementation minimal.

## Storage rules

Use config values:

* `STORAGE_BACKEND = "local"`
* `LOCAL_STORAGE_DIR = "storage/uploads"`

Original uploaded files should be saved under a path like:

```text
backend/storage/uploads/workspaces/<workspace_id>/sources/<data_source_id>/original/<file_id>__<safe_original_filename>
```

The exact path can vary slightly, but it must include:

* workspace_id
* data_source_id
* file_id
* safe original filename

For MVP, derived dataset tables do not need to be materialized to Parquet yet unless already easy. It is acceptable to parse directly from the uploaded file for preview.

## In-memory repositories

Create simple in-memory repositories for this milestone.

Suggested files:

```text
backend/app/repositories/memory.py
```

or separate files:

```text
backend/app/repositories/data_source_repository.py
backend/app/repositories/dataset_repository.py
backend/app/repositories/context_document_repository.py
```

Use simple dictionaries keyed by UUID.

This is temporary. Do not add SQLAlchemy or database persistence yet.

Repository must support storing/retrieving:

* DataSource
* UploadedFile
* Dataset
* DatasetSource
* DatasetVersion
* DatasetTable
* ContextDocument

## File tools

Create file utilities in:

```text
backend/app/tools/files/
```

Suggested files:

```text
storage.py
csv_loader.py
excel_loader.py
text_loader.py
filename.py
```

Required behavior:

### Filename safety

Implement a helper that converts uploaded filenames into safe filenames.

It should prevent:

* path traversal
* absolute paths
* weird separators

Example:

```text
../../sales.csv → sales.csv
May Sales Report.xlsx → May_Sales_Report.xlsx
```

### CSV loader

Given a local file path:

* read CSV
* infer column names
* return preview rows
* return row count
* return column count
* return DatasetTable metadata

Use pandas if available.

### Excel loader

Given a local file path:

* read workbook sheet names
* support multiple sheets
* return previews for each sheet
* return row/column counts per sheet
* create one DatasetTable per sheet

Use openpyxl or pandas.

### Text loader

Given a local file path:

* read text content
* create ContextDocument
* optionally return a short preview
* do not summarize with LLM yet

Support `.txt` and `.md`.

## API routes

Add routes under:

```text
backend/app/api/routes/uploads.py
```

or separate routes if cleaner.

Minimum endpoints:

### Upload tabular file

```text
POST /workspaces/{workspace_id}/datasets/upload
```

Accept multipart file.

Supported extensions:

* `.csv`
* `.xlsx`
* `.xls`

Behavior:

1. Create DataSource with `source_kind = uploaded_file`.
2. Create UploadedFile with file metadata and storage path.
3. Create Dataset.
4. Link Dataset to DataSource through DatasetSource with role `primary`.
5. Create DatasetVersion:

   * version_number = 1
   * version_type = original
   * display_name = "Original upload"
   * parent_version_id = null
6. Create DatasetTable records:

   * one table for CSV
   * one table per Excel sheet
7. Return upload response with:

   * dataset
   * data_source
   * uploaded_file
   * dataset_version
   * dataset_tables
   * preview data

For dataset name, use either:

* request field `dataset_name`, if provided
* otherwise safe filename without extension

### Upload context file

```text
POST /workspaces/{workspace_id}/context-documents/upload
```

Accept multipart text/markdown file.

Supported extensions:

* `.txt`
* `.md`

Behavior:

1. Create DataSource with `source_kind = uploaded_file`.
2. Create UploadedFile.
3. Create ContextDocument linked to DataSource.
4. Store raw text path.
5. Return context document metadata and preview.

Do not generate `ContextSummary` yet.

## Response schemas

Use existing schemas where possible.

If needed, create:

```text
DatasetUploadResponse
ContextDocumentUploadResponse
TablePreview
```

Keep them small.

## Frontend

Add minimal UI placeholders only if cheap:

* file input for dataset upload
* file input for context upload

No need for polished UI.

It is acceptable to leave frontend mostly placeholder if backend upload is complete.

## Tests

Add tests for:

### Filename safety

* prevents path traversal
* handles spaces
* preserves extension

### CSV upload

Use a small fixture CSV.

Assert:

* DataSource created
* UploadedFile created
* Dataset created
* DatasetSource created
* DatasetVersion created with `version_number = 1`, `version_type = original`
* DatasetTable created
* preview rows returned
* file exists on disk

### Excel upload

Use a small fixture Excel file with 2 sheets.

Assert:

* one Dataset created
* one DatasetVersion created
* two DatasetTable records created
* previews returned for both sheets

### Context upload

Use a small `.txt` or `.md` fixture.

Assert:

* DataSource created
* UploadedFile created
* ContextDocument created
* file exists on disk
* preview returned

### Unsupported file type

Assert unsupported extension returns clear error.

## Test fixtures

Create small fixtures under:

```text
backend/app/tests/fixtures/
```

Suggested:

```text
simple_sales.csv
multi_sheet_sales.xlsx
company_context.txt
```

If generating Excel fixture in test is easier than committing a binary file, generate it inside the test with pandas/openpyxl.

## Error handling

Return clear errors for:

* missing file
* unsupported extension
* empty file
* parse failure
* unsafe filename

Do not expose internal stack traces in API responses.

## Acceptance criteria

Milestone 2 is complete when:

1. CSV upload works.
2. Excel upload works with multiple sheets.
3. Text/markdown context upload works.
4. Uploaded files are saved under local storage.
5. Correct domain objects are created in memory.
6. Preview data is returned.
7. Tests pass.
8. No profiling, cleaning, features, visualization, LLM calls, auth, or database persistence is implemented.

## Keep response concise

When done, summarize only:

* files changed
* endpoints added
* tests added
* commands to run
* limitations