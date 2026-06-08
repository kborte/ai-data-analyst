# Milestone 4: Cleaning Plan Generation

## Goal

Implement deterministic cleaning plan generation.

Given an existing `DataProfile`, the system should produce a `CleaningPlan` containing JSON-based proposed cleaning steps.

This milestone does **not** apply cleaning. It only recommends cleaning actions and stores/retrieves the plan.

## Scope

Milestone 4 is split into four implementation parts:

1. M4A — deterministic cleaning rule engine
2. M4B — cleaning plan service and in-memory storage
3. M4C — cleaning plan API route
4. M4D — optional minimal frontend preview

Each part should be implemented separately.

Do not implement cleaning decisions, cleaning execution, dataset mutation, new dataset versions, feature engineering, visualization, LLM calls, database persistence, authentication, or external integrations.

---

# M4A: Cleaning Rule Engine

## Goal

Implement only the deterministic rule engine that converts a `DataProfile` into a list of `CleaningStep` objects.

## Files

Suggested files:

```text
backend/app/tools/data/cleaning_rule_engine.py
backend/app/tests/unit/test_cleaning_rule_engine.py
```

## Input

The rule engine should accept a `DataProfile`.

## Output

The rule engine should return:

```text
list[CleaningStep]
```

Use existing cleaning schemas from:

```text
backend/app/schemas/cleaning.py
```

## Behavior

Convert existing `DataQualityIssue` objects into cleaning recommendations.

### missing_values

If missing values affect a likely metric/date/id column:

* operation: `drop_rows_with_missing` or `drop_rows_with_missing_key_fields`
* requires_human_approval: true
* default_decision: `needs_review`
* impact_level: high or critical
* affects_key_metrics: true if metric column

If missing values affect a likely categorical column:

* operation: `fill_missing_constant`
* fill value: `"Unknown"`
* requires_human_approval: true if `affected_rows_percent >= 10`, otherwise false
* default_decision: `needs_review` if approval required, otherwise `approved`

If missing values affect a low-importance column:

* operation: `ignore_issue`
* requires_human_approval: false
* default_decision: `approved`

### duplicate_rows

* operation: `remove_exact_duplicates`
* requires_human_approval: true
* default_decision: `needs_review`
* affects_key_metrics: true
* impact_level: high

### whitespace

* operation: `trim_whitespace`
* requires_human_approval: false
* default_decision: `approved`

### inconsistent_categories

* operation: `standardize_categories`
* requires_human_approval: true
* default_decision: `needs_review`

### numeric_stored_as_text

If likely metric:

* operation: `convert_numeric`
* requires_human_approval: true
* default_decision: `needs_review`

Otherwise:

* operation: `convert_numeric`
* requires_human_approval: false
* default_decision: `approved`

### date_stored_as_text

* operation: `parse_dates`
* requires_human_approval: true if likely date, otherwise false
* default_decision: `needs_review` if approval required, otherwise `approved`

### high_cardinality_category

* operation: `ignore_issue`
* requires_human_approval: false
* default_decision: `approved`

### mixed_types

* operation: `ignore_issue`
* requires_human_approval: true
* default_decision: `needs_review`

## CleaningStep shape

Each generated step must include:

```text
step_id
sequence_order
issue
recommendation
operation
preview
```

Step IDs should be stable and readable.

Example:

```text
clean_001_missing_values_orders_revenue
```

## Human-in-the-loop rule

Require human approval when:

* operation changes row count
* issue affects a likely metric/id/date column
* affected_rows_percent >= 10
* operation changes a grouping/filtering/pivot column
* issue could affect key metrics

Auto-approve or auto-ignore only when:

* issue is low-impact
* affected_rows_percent < 10
* column is not likely metric/id/date
* issue does not affect joins/pivots/filters

## M4A Tests

Add focused unit tests using constructed `DataProfile` objects.

Test cases:

1. missing revenue requires approval
2. missing notes/internal text is ignored/default approved
3. duplicate rows require approval
4. whitespace defaults to approved
5. numeric stored as text in revenue requires approval
6. date stored as text in date column requires approval
7. high-cardinality category is ignored
8. generated steps have stable sequence order and valid schema

## M4A Acceptance Criteria

M4A is complete when:

* `CleaningRuleEngine` exists
* it converts profile issues into cleaning steps
* no API/routes/services are added
* no cleaning execution is implemented
* tests pass

---

# M4B: Cleaning Plan Service and In-Memory Storage

## Goal

Implement the service layer for creating and storing cleaning plans.

Given a profile, the service should retrieve the existing `DataProfile`, call `CleaningRuleEngine`, construct `CleaningPlanJson`, wrap it in `CleaningPlan`, save it in memory, and return it.

## Files

Suggested files:

```text
backend/app/services/cleaning_plan_service.py
backend/app/repositories/memory.py
backend/app/tests/unit/test_cleaning_plan_service.py
```

Adjust names if your existing repository/service naming differs.

## Behavior

Implement `CleaningPlanService`.

Suggested method:

```python
create_cleaning_plan(
    workspace_id: UUID,
    dataset_id: UUID,
    dataset_version_id: UUID,
    profile_id: UUID,
    created_by_user_id: UUID,
) -> CleaningPlan
```

Exact signature can be adapted to existing schemas and repository patterns.

Service flow:

1. Retrieve `DataProfile` from repository.
2. Validate that the profile exists.
3. Call `CleaningRuleEngine`.
4. Build `CleaningPlanJson`.
5. Build `CleaningPlan`.
6. Save `CleaningPlan` in repository.
7. Return `CleaningPlan`.

## CleaningPlanJson requirements

Include:

```text
schema_version
plan_id
dataset_version_id
profile_id
status
created_at
summary
global_assumptions
steps
```

Summary should include:

```text
total_steps
steps_requiring_approval
auto_approved_steps
auto_ignored_steps
estimated_row_count_change
estimated_columns_changed
```

## Repository requirements

Add minimal in-memory support for:

```text
save cleaning plan
get cleaning plan by id
get cleaning plans by dataset version, if simple
```

Do not introduce database persistence.

## M4B Tests

Use fake/in-memory profiles.

Test:

1. service creates a cleaning plan from profile
2. plan is saved in repository
3. summary counts are correct
4. empty profile issues produce a valid plan with zero steps
5. missing profile raises clear domain error or ValueError

## M4B Acceptance Criteria

M4B is complete when:

* `CleaningPlanService` exists
* cleaning plans can be created from profiles
* cleaning plans are saved in memory
* tests pass
* no routes/API endpoints are added
* no cleaning execution is implemented

---

# M4C: Cleaning Plan API Route

## Goal

Add a thin API route for generating a cleaning plan from an existing profile/dataset version.

## Files

Suggested files:

```text
backend/app/api/routes/cleaning.py
backend/app/main.py
backend/app/tests/unit/test_cleaning_api.py
```

Adjust names if existing API conventions differ.

## Endpoint

Add:

```text
POST /datasets/{dataset_id}/versions/{dataset_version_id}/cleaning-plans
```

Suggested request body:

```json
{
  "workspace_id": "uuid",
  "profile_id": "uuid",
  "created_by_user_id": "uuid"
}
```

If the project already has a better request schema, use it.

Behavior:

1. Route receives request.
2. Route calls `CleaningPlanService`.
3. Route returns `CleaningPlan`.

The route must be thin.

## Optional endpoint

If simple, add:

```text
GET /cleaning-plans/{cleaning_plan_id}
```

This should retrieve a saved cleaning plan.

Do not overbuild list endpoints.

## M4C Tests

Add API tests.

Test:

1. POST creates and returns cleaning plan
2. returned plan contains expected steps
3. missing profile returns clear error
4. route does not execute cleaning

## M4C Acceptance Criteria

M4C is complete when:

* cleaning route exists
* cleaning plan can be created through API
* route test passes
* route remains thin
* no cleaning execution or dataset mutation exists

---

# M4D: Optional Minimal Frontend Cleaning Plan Preview

## Goal

Add a minimal frontend view for cleaning plan results.

This is optional. Do not implement if backend M4A–M4C are not stable.

## Scope

Show cleaning plan steps in a readable format.

Each step should show:

```text
issue description
recommended action
affected rows percent
impact level
requires approval
default decision
rationale
```

## Do not implement

* approval
* editing
* execution
* dataset mutation
* polished dashboard UI

## M4D Acceptance Criteria

M4D is complete when:

* user can see cleaning plan steps
* high-impact steps are visually distinguishable
* no approval/execution logic is implemented

---

# Milestone 4 Global Acceptance Criteria

Milestone 4 is complete when:

1. A `DataProfile` can be converted into a deterministic cleaning plan.
2. Cleaning steps are generated using existing profile issues.
3. Cleaning plan is saved in memory.
4. Cleaning plan can be created through an API route.
5. No cleaning execution is implemented.
6. No dataset version is mutated or created.
7. No LLM calls are used.
8. Tests pass.
