# Milestone 3: Deterministic Data Profiling

## Goal

Implement deterministic profiling for uploaded dataset versions.

Given a `DatasetVersion`, the system should inspect its table(s) and create a `DataProfile` artifact.

This milestone should answer:

> Can the app inspect an uploaded CSV/Excel dataset version and produce reliable metadata about columns, types, missing values, uniqueness, sample values, and obvious data quality issues?

## Scope

Build profiling for tabular dataset versions created in Milestone 2.

Support:

* CSV-backed dataset versions
* Excel-backed dataset versions with multiple tables/sheets
* dataset table profiling
* column-level profiling
* basic data quality issue detection
* in-memory profile storage
* API endpoint to create/get a profile
* tests with fixture datasets

Do not implement cleaning plans, cleaning execution, feature engineering, visualization, interpretation, LLM calls, database persistence, authentication, or external integrations.

## Architecture rules

Follow `CLAUDE.md`.

Important:

* Keep routes thin.
* Put profiling workflow in a service.
* Put low-level dataframe profiling in tools.
* Store profile artifacts through repositories.
* Profiling must be deterministic.
* Do not call any LLM.
* Do not mutate dataset versions.
* Do not create cleaned/enriched versions.
* Do not perform heavy analysis beyond profiling and basic issue detection.

## Suggested files

Add or update:

```text
backend/app/api/routes/profiles.py
backend/app/services/profiling_service.py
backend/app/tools/data/profiler.py
backend/app/repositories/memory.py
backend/app/tests/unit/test_profiler.py
backend/app/tests/unit/test_profiles_api.py
```

Adjust names if the existing project structure uses different conventions.

## API endpoints

Add:

```text
POST /datasets/{dataset_id}/versions/{dataset_version_id}/profile
```

Behavior:

1. Find the `DatasetVersion`.
2. Load its associated `DatasetTable` records.
3. Read table data from the original uploaded file or table storage path.
4. Generate a `DataProfile`.
5. Store the profile in the in-memory repository.
6. Return the profile.

Optional if easy:

```text
GET /profiles/{profile_id}
```

Do not overbuild list/search endpoints yet.

## DataProfile expectations

Use the existing `DataProfile`, `ColumnProfile`, `NumericSummary`, `DateSummary`, and `DataQualityIssue` schemas from Milestone 1.

If schema adjustments are needed, keep them minimal and compatible.

The profile should include:

```text
profile_id
dataset_version_id
row_count
column_count
columns
detected_issues
likely_id_columns
likely_metric_columns
likely_categorical_columns
likely_date_columns
created_at
```

For multi-sheet Excel datasets, either:

1. include table-level information inside metadata/json fields, or
2. return one combined profile with column profiles carrying `table_name`.

Choose the simpler option consistent with the existing schemas.

## ColumnProfile requirements

For each column, compute:

```text
column_name
inferred_type
missing_count
missing_percent
unique_count
sample_values
numeric_summary, if numeric
date_summary, if date/datetime
is_likely_id
is_likely_metric
is_likely_categorical
is_likely_date
```

If the same column name appears in different tables, distinguish using table name if the schema supports it. If not, use a stable label such as:

```text
orders.revenue
customers.country
```

## Type inference

Implement deterministic, simple type inference.

Supported inferred types:

```text
string
integer
float
boolean
date
datetime
categorical
unknown
```

Rules can be simple:

* Numeric pandas dtype → integer/float
* Boolean dtype → boolean
* Parseable date-like values → date/datetime
* Object/string with low cardinality → categorical
* Object/string otherwise → string
* Empty/ambiguous columns → unknown

Avoid being too clever. Profiling can improve later.

## NumericSummary

For numeric columns, compute:

```text
min
max
mean
median
std
```

Use `None` where not applicable.

## DateSummary

For date/datetime columns, compute:

```text
min_date
max_date
```

If the existing schema has different field names, follow the schema.

## Likely column heuristics

Implement simple heuristics.

### Likely ID column

Mark `is_likely_id = true` if:

* column name contains `id`, or
* unique percent is very high, for example above 90%

But avoid marking numeric metric columns as IDs only because they are unique.

### Likely metric column

Mark `is_likely_metric = true` if:

* numeric column
* column name suggests metric, e.g. `revenue`, `sales`, `amount`, `price`, `cost`, `spend`, `orders`, `quantity`, `users`, `count`, `profit`, `margin`

### Likely categorical column

Mark `is_likely_categorical = true` if:

* non-numeric with relatively low unique count, or
* column name suggests category, e.g. `country`, `region`, `channel`, `campaign`, `product`, `status`, `segment`

### Likely date column

Mark `is_likely_date = true` if:

* inferred type is date/datetime, or
* column name contains `date`, `time`, `created_at`, `updated_at`, `timestamp`

## Data quality issues

Detect basic issues only:

```text
missing_values
duplicate_rows
numeric_stored_as_text
date_stored_as_text
high_cardinality_category
mixed_types
```

Do not create cleaning steps yet. Only create `DataQualityIssue` objects.

### Missing values

Create issue if a column has missing values.

Impact:

* high if likely metric/date/id
* medium if likely categorical
* low otherwise

### Duplicate rows

Create issue if exact duplicate rows exist in a table.

Impact:

* high if duplicate percent is nontrivial
* medium otherwise

### Numeric stored as text

Create issue if a string/object column has many values parseable as numbers.

### Date stored as text

Create issue if a string/object column has many values parseable as dates.

### High-cardinality category

Create issue if a likely categorical/string column has unusually high unique count.

### Mixed types

Create issue if an object/string column contains a suspicious mix of numeric-looking, date-looking, and text values.

Keep heuristics simple and tested.

## Profile service flow

`ProfilingService` should:

1. Accept `dataset_id` and `dataset_version_id`.
2. Retrieve the dataset version and tables from repository.
3. Load each table’s data using existing file/table loading utilities.
4. Call `Profiler`.
5. Build `DataProfile`.
6. Save `DataProfile`.
7. Return `DataProfile`.

The route should not directly use pandas.

## Tests

Add tests for deterministic profiling.

Use small fixtures.

Test cases:

### Basic CSV profile

Fixture: `simple_sales.csv`

Assert:

* row count correct
* column count correct
* revenue detected as numeric/metric
* date detected as date/likely date
* status/product/channel detected as categorical if present

### Missing values

Fixture or generated dataframe with missing revenue/country.

Assert:

* missing count correct
* missing percent correct
* missing value issue generated
* missing revenue has higher impact than missing notes/text column

### Duplicate rows

Assert:

* duplicate row issue generated
* affected row count correct

### Numeric stored as text

Example values:

```text
"100"
"200"
"300"
```

Assert issue is detected.

### Date stored as text

Example values:

```text
"2026-01-01"
"2026-01-02"
```

Assert likely date/date-stored-as-text is detected.

### Excel multi-sheet profile

Use generated Excel fixture with two sheets.

Assert:

* profile includes both tables/sheets
* row/column counts are correct enough
* no crash

### API test

Call:

```text
POST /datasets/{dataset_id}/versions/{dataset_version_id}/profile
```

Assert:

* status 200
* profile returned
* profile saved in repository

Use existing in-memory objects/fixtures from upload tests if available.

## Error handling

Return clear errors for:

* dataset version not found
* no tables found for dataset version
* file missing from storage
* unsupported table source
* parsing/profiling failure

Do not expose internal stack traces.

## Acceptance criteria

Milestone 3 is complete when:

1. A dataset version can be profiled.
2. CSV profiling works.
3. Excel multi-sheet profiling works.
4. Column profiles are generated.
5. Basic data quality issues are detected.
6. Profile artifact is saved in memory.
7. API endpoint returns profile.
8. Tests pass.
9. No cleaning, feature engineering, visualization, LLM calls, auth, database persistence, or integrations are implemented.

## Keep response concise

When done, summarize only:

* files changed
* endpoints added
* tests added
* commands to run
* limitations
