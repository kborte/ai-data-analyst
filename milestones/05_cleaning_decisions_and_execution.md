# Milestone 5: Cleaning Decisions and Execution

## Goal

Implement human-in-the-loop cleaning execution.

Given an existing `CleaningPlan`, the system should:

1. Accept user decisions for each cleaning step.
2. Validate that required approvals are present.
3. Execute approved cleaning operations deterministically.
4. Create a new cleaned `DatasetVersion`.
5. Save a `CleaningResult` with an execution log.
6. Preserve the original dataset version unchanged.

This milestone moves from “suggested fixes” to “approved fixes applied safely.”

## Scope

Milestone 5 is split into five implementation parts:

1. M5A — cleaning decision schemas/helpers and validation
2. M5B — deterministic cleaning executor tool
3. M5C — cleaning execution service and repository storage
4. M5D — cleaning decisions/execution API routes
5. M5E — optional frontend approval/execution UI

Each part should be implemented separately.

Do not implement feature engineering, visualization, insight generation, LLM calls, database persistence, authentication, or external integrations.

---

# M5A: Cleaning Decisions and Validation

## Goal

Implement decision validation logic for cleaning plans.

Given a `CleaningPlan` and user decisions, the system should determine which steps are approved, rejected, modified, or blocked.

Do not execute cleaning in this part.

## Files

Suggested files:

```text
backend/app/tools/data/cleaning_decision_resolver.py
backend/app/tests/unit/test_cleaning_decision_resolver.py
```

Update schemas only if required:

```text
backend/app/schemas/cleaning.py
```

## Inputs

* `CleaningPlan`
* user-provided `CleaningDecisions` or `CleaningDecisionsJson`

## Outputs

A resolved list of cleaning decisions that can later be passed to the executor.

## Decision values

Support:

```text
approved
rejected
modified
```

If existing enums use different names, follow the current codebase.

## Decision resolution rules

For each cleaning step:

1. If the user explicitly approved the step, execute it as written.
2. If the user explicitly rejected the step, skip it.
3. If the user modified the step, use the modified operation after validation.
4. If no user decision exists:

   * if `requires_human_approval = true`, block execution
   * otherwise use the step’s `default_decision`
5. If a step defaults to `approved`, it may execute without explicit approval.
6. If a step defaults to `needs_review`, it must not execute without user approval.
7. If a step defaults to `ignored` or operation is `ignore_issue`, skip it.

## Validation rules

Reject decisions when:

* decision references a step ID that does not exist
* required approval is missing
* modified operation changes the operation type to an unsupported operation
* modified operation has invalid parameters
* duplicate decisions are submitted for the same step

## Decision summary

Return a summary containing:

```text
total_steps
approved_steps
rejected_steps
modified_steps
blocked_steps
auto_approved_steps
skipped_steps
can_execute
```

## Tests

Add focused unit tests.

Test cases:

1. required approval missing blocks execution
2. explicit approval allows required step
3. explicit rejection skips step
4. default-approved low-risk step executes without approval
5. ignore issue is skipped
6. unknown step ID is rejected
7. duplicate decisions are rejected
8. modified step validates operation type
9. summary counts are correct

## M5A Acceptance Criteria

M5A is complete when:

* cleaning decision resolver exists
* required approvals are enforced
* resolved decisions are deterministic
* invalid decisions are rejected
* tests pass
* no cleaning execution is implemented

---

# M5B: Deterministic Cleaning Executor Tool

## Goal

Implement the low-level cleaning executor.

Given table data and resolved approved cleaning operations, apply supported cleaning operations deterministically.

Do not create dataset versions in this part.
Do not add API routes in this part.
Do not use LLMs.

## Files

Suggested files:

```text
backend/app/tools/data/cleaning_executor.py
backend/app/tests/unit/test_cleaning_executor.py
```

## Inputs

* one or more loaded tables, likely as pandas DataFrames
* resolved cleaning steps/operations

## Outputs

* cleaned table data
* per-step execution results
* execution summary

## Supported operations

Implement only these operations for M5:

```text
ignore_issue
drop_rows_with_missing
drop_rows_with_missing_key_fields
fill_missing_constant
remove_exact_duplicates
trim_whitespace
convert_numeric
parse_dates
standardize_categories
```

If existing operation enum names differ, adapt to current codebase.

## Operation behavior

### ignore_issue

Do nothing. Mark step as skipped.

### drop_rows_with_missing

Drop rows where selected column(s) are missing.

Parameters:

```json
{
  "table_name": "orders",
  "columns": ["revenue"]
}
```

### drop_rows_with_missing_key_fields

Same as `drop_rows_with_missing`, but used for higher-risk key fields.

### fill_missing_constant

Fill missing values in selected column with a constant.

Parameters:

```json
{
  "table_name": "orders",
  "column": "country",
  "value": "Unknown"
}
```

### remove_exact_duplicates

Remove exact duplicate rows from a table.

Parameters:

```json
{
  "table_name": "orders"
}
```

### trim_whitespace

Trim leading/trailing whitespace in selected string columns.

Parameters:

```json
{
  "table_name": "orders",
  "columns": ["product_name"]
}
```

### convert_numeric

Convert selected column to numeric.

Parameters:

```json
{
  "table_name": "orders",
  "column": "revenue"
}
```

Use safe conversion. Invalid values should become null/NaN unless existing parameter says otherwise.

### parse_dates

Parse selected column as date/datetime.

Parameters:

```json
{
  "table_name": "orders",
  "column": "order_date"
}
```

Use safe parsing. Invalid values should become null/NaT unless existing parameter says otherwise.

### standardize_categories

Implement simple mapping-based standardization only.

Parameters:

```json
{
  "table_name": "orders",
  "column": "status",
  "mapping": {
    "complete": "Completed",
    "completed": "Completed",
    "COMPLETE": "Completed"
  }
}
```

Do not invent mappings automatically in M5.

## Safety rules

* Never mutate the input DataFrame in place.
* Return cleaned copies.
* Preserve column order where possible.
* Preserve table names.
* If one operation fails, record the failure.
* For M5, it is acceptable to stop execution on first failed operation.
* Do not execute arbitrary Python.
* Do not evaluate arbitrary formulas.

## Step result

Each executed step should produce a result containing:

```text
step_id
operation_type
status
rows_before
rows_after
rows_changed
rows_removed
columns_changed
message
error
```

Status should support:

```text
executed
skipped
failed
```

Use existing schema enums if available.

## Tests

Add focused tests using small in-test DataFrames.

Test cases:

1. drop rows with missing revenue
2. fill missing country with Unknown
3. remove exact duplicates
4. trim whitespace in product names
5. convert numeric stored as text
6. parse dates stored as text
7. standardize categories using explicit mapping
8. ignore issue does not change data
9. input DataFrame is not mutated
10. execution log records row/column changes

## M5B Acceptance Criteria

M5B is complete when:

* cleaning executor exists
* supported operations work deterministically
* input data is not mutated
* per-step results are generated
* tests pass
* no service/API/dataset version creation is implemented

---

# M5C: Cleaning Execution Service and Dataset Version Creation

## Goal

Implement the service layer that applies approved cleaning steps to a dataset version and creates a new cleaned dataset version.

This connects:

```text
CleaningPlan
+ CleaningDecisions
+ CleaningDecisionResolver
+ CleaningExecutor
+ DatasetVersion creation
+ CleaningResult
```

## Files

Suggested files:

```text
backend/app/services/cleaning_execution_service.py
backend/app/repositories/memory.py
backend/app/tests/unit/test_cleaning_execution_service.py
```

Update storage/table utilities only if needed.

## Behavior

Implement `CleaningExecutionService`.

Suggested method:

```python
execute_cleaning_plan(
    workspace_id: UUID,
    dataset_id: UUID,
    input_dataset_version_id: UUID,
    cleaning_plan_id: UUID,
    decisions: CleaningDecisions,
    executed_by_user_id: UUID,
) -> CleaningResult
```

Exact signature may be adapted to existing schemas.

## Service flow

1. Retrieve input `DatasetVersion`.
2. Retrieve `CleaningPlan`.
3. Validate that the plan belongs to the input dataset version.
4. Resolve user decisions with `CleaningDecisionResolver`.
5. If execution is blocked, return or raise a clear validation error.
6. Load original table data for the input dataset version.
7. Execute approved cleaning operations using `CleaningExecutor`.
8. Persist cleaned table data to local derived storage.
9. Create a new `DatasetVersion`:

   * `parent_version_id = input_dataset_version_id`
   * `version_number = next version number for dataset`
   * `version_type = cleaned`
   * `display_name = "Cleaned data"`
   * `description = "Created by applying approved cleaning steps"`
   * `row_count`
   * `column_count`
   * `storage_path`, if applicable
10. Create corresponding `DatasetTable` records for cleaned output tables.
11. Create and save `CleaningResult`.
12. Return `CleaningResult`.

## Storage rules

Original uploaded files must remain unchanged.

Cleaned outputs should be saved separately under derived storage.

Suggested path:

```text
backend/storage/uploads/workspaces/{workspace_id}/datasets/{dataset_id}/versions/{dataset_version_id}/tables/{table_name}.csv
```

If the existing project has a storage utility, use it.

For M5, saving cleaned tables as CSV is acceptable.

## CleaningResult requirements

`CleaningResult` should include:

```text
cleaning_result_id
cleaning_plan_id
input_dataset_version_id
output_dataset_version_id
status
execution_log_json
created_at
created_by_user_id
```

`execution_log_json` should include:

```text
schema_version
cleaning_run_id
cleaning_plan_id
input_dataset_version_id
output_dataset_version_id
started_at
completed_at
status
summary
step_results
warnings
```

Summary should include:

```text
total_steps
executed_steps
skipped_steps
failed_steps
rows_before
rows_after
rows_removed
columns_changed
```

## Failure behavior

For M5:

* If required approval is missing, do not execute anything.
* If table loading fails, do not create output dataset version.
* If execution fails before output is saved, do not create output dataset version.
* If one step fails during execution, stop and return/save a failed `CleaningResult` only if the current schema supports failed results safely.
* Prefer not creating a cleaned dataset version on failure.

## Tests

Use small fake repository objects and small table fixtures.

Test cases:

1. approved cleaning plan creates new cleaned dataset version
2. original dataset version remains unchanged
3. output version parent points to input version
4. output version type is cleaned
5. missing required approval blocks execution
6. cleaning result is saved
7. execution log includes step results
8. version number increments correctly
9. cleaned table data is saved separately
10. failed execution does not create cleaned dataset version

## M5C Acceptance Criteria

M5C is complete when:

* cleaning execution service exists
* approved steps can be executed through the service
* new cleaned dataset version is created
* original dataset version is preserved
* cleaning result is saved
* tests pass
* no API routes are added in this part

---

# M5D: Cleaning Decisions and Execution API Routes

## Goal

Add thin API routes for submitting cleaning decisions and executing a cleaning plan.

Do not put cleaning logic inside routes.

## Files

Suggested files:

```text
backend/app/api/routes/cleaning_execution.py
backend/app/main.py
backend/app/tests/unit/test_cleaning_execution_api.py
```

If the existing cleaning route file should be reused, use that instead.

## Endpoints

Add:

```text
POST /cleaning-plans/{cleaning_plan_id}/decisions/validate
```

Purpose:

Validate user decisions before execution.

Request body:

```json
{
  "workspace_id": "uuid",
  "dataset_id": "uuid",
  "dataset_version_id": "uuid",
  "created_by_user_id": "uuid",
  "decisions": [
    {
      "step_id": "clean_001_missing_values_orders_revenue",
      "decision": "approved",
      "comment": "Revenue is required for the analysis."
    }
  ]
}
```

Response:

* decision validation summary
* whether execution can proceed
* blocked steps, if any

Add:

```text
POST /cleaning-plans/{cleaning_plan_id}/execute
```

Purpose:

Execute approved cleaning decisions.

Request body:

```json
{
  "workspace_id": "uuid",
  "dataset_id": "uuid",
  "input_dataset_version_id": "uuid",
  "executed_by_user_id": "uuid",
  "decisions": [
    {
      "step_id": "clean_001_missing_values_orders_revenue",
      "decision": "approved"
    }
  ]
}
```

Response:

* `CleaningResult`
* output cleaned dataset version ID

Optional if simple:

```text
GET /cleaning-results/{cleaning_result_id}
```

Do not overbuild list endpoints.

## Route rules

Routes should:

1. Parse request.
2. Call service/resolver.
3. Return response.

Routes should not:

* use pandas
* load table files
* apply cleaning
* create dataset versions directly
* manipulate repositories directly beyond dependency wiring

## Tests

Add API tests.

Test cases:

1. validate decisions returns can_execute true when approvals present
2. validate decisions returns can_execute false when required approvals missing
3. execute route creates cleaning result
4. execute route returns output dataset version id
5. execute route does not mutate original version
6. route returns clear error for missing cleaning plan

## M5D Acceptance Criteria

M5D is complete when:

* decision validation API exists
* cleaning execution API exists
* routes are thin
* API tests pass
* no cleaning logic is placed in routes

---

# M5E: Optional Frontend Approval and Execution UI

## Goal

Add a minimal frontend flow for reviewing suggested fixes, approving/skipping them, and executing cleaning.

This should be beginner-friendly and avoid internal technical terms.

## Scope

The UI should show each suggested fix with:

```text
what was found
why it matters
suggested action
risk level
whether review is required
Approve / Skip controls
```

## User-facing language

Use beginner-friendly labels.

Prefer:

```text
Suggested fixes
Needs your review
Safe to apply automatically
Apply selected fixes
Skip this fix
What will change
```

Avoid exposing:

```text
CleaningPlanJson
operation_type
DatasetVersion
execution_log_json
artifact
schema
metadata
```

Technical details can be hidden under:

```text
Show details
Advanced
```

## Flow

1. User views cleaning plan.
2. User approves/skips required steps.
3. User clicks `Apply selected fixes`.
4. Frontend calls execution endpoint.
5. User sees:

   * fixes applied
   * rows removed/changed
   * new cleaned copy created
   * original file unchanged

## Do not implement

* complex editing
* custom mappings UI
* polished dashboard
* feature engineering
* charts
* insight generation

## M5E Acceptance Criteria

M5E is complete when:

* user can approve or skip cleaning steps
* user can apply approved fixes
* UI uses beginner-friendly language
* user can see that a cleaned copy was created
* original file is not presented as overwritten

---

# Milestone 5 Global Acceptance Criteria

Milestone 5 is complete when:

1. User decisions can be submitted for a cleaning plan.
2. Required approvals are enforced.
3. Approved cleaning operations execute deterministically.
4. Original dataset version is preserved.
5. A new cleaned dataset version is created.
6. A cleaning result with execution log is saved.
7. API routes can validate decisions and execute cleaning.
8. Tests pass.
9. No LLM calls are used.
10. No feature engineering, visualization, or insight generation is implemented.
