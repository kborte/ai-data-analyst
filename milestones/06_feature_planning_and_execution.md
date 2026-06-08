# Milestone 6: Feature Engineering

## Goal

Suggest and apply simple calculated metrics/features.

No LLM calls. No charts. No insights. No frontend. No database.

Use this model:

FeaturePlan = immutable proposal
FeatureDecisions = user approvals/rejections
FeatureResult = execution log
DatasetVersion = new enriched copy

Do not mutate previous dataset versions.
Do not mutate `FeaturePlan.plan_json.features` to store approvals.

---

## M6A: Schemas + Planner

Implement feature schemas if missing or broken.

Use broad operation types only:

* ratio
* arithmetic
* aggregate
* window
* period_change
* date_extract
* bucketize
* custom_formula

Do not create one enum per metric.

`custom_formula` is allowed in schemas only. It must not execute in M6.

Planner input: `DataProfile`.

Planner output: feature suggestions.

Suggest only obvious features:

* date parts from date columns
* AOV if revenue + order/order_id exist
* ARPU if revenue + user/customer id exist
* running revenue if date + revenue exist
* running revenue by channel/campaign if date + revenue + channel/campaign exist
* revenue by category if categorical + revenue exist

Every suggestion must require approval.

Max suggestions: 8.

Feature suggestions must include:

* feature_id
* feature_name
* display_name
* operation_type
* formula_display
* input_table
* output_table or output_column
* required_columns
* parameters
* requires_human_approval

Tests:

* schemas validate ratio/window/aggregate features
* custom_formula validates in schema but is marked unsupported for execution
* revenue + order_id suggests AOV
* date + revenue suggests running revenue
* date + revenue + channel suggests grouped running revenue
* all suggestions require approval
* max suggestions respected

---

## M6B: Executor

Implement deterministic feature executor.

Input: dict of table_name -> pandas DataFrame, plus approved feature definitions.

Output: enriched table copies + execution results.

Supported operations:

* ratio
* arithmetic
* aggregate
* window
* period_change
* date_extract
* bucketize

Rules:

* never mutate input DataFrames
* no arbitrary Python
* no custom_formula execution
* validate required columns
* return failed result for missing columns
* return failed result for custom_formula
* tests use small in-test DataFrames

Aggregate operations may create a new output table.
Column operations should add columns to the existing input table.

Tests:

* ratio creates AOV
* divide by zero is safe
* arithmetic creates net revenue
* aggregate creates revenue_by_channel table
* window creates running revenue
* date_extract creates year/month/week/weekday
* bucketize creates bucket column
* custom_formula returns failed result
* input DataFrame is not mutated

---

## M6C: Service + API

Implement feature service and thin API routes.

Service should:

1. create feature plan from profile
2. validate decisions
3. execute approved features
4. save enriched tables separately
5. create new `DatasetVersion` with `version_type = enriched`
6. save `FeatureResult`

Approval rules:

* execute only approved features
* skip rejected features
* block execution if any feature requiring approval has no decision
* do not mutate `FeaturePlan`
* save decisions separately if existing schemas support it

Routes:

POST /datasets/{dataset_id}/versions/{dataset_version_id}/feature-plans

POST /feature-plans/{feature_plan_id}/decisions/validate

POST /feature-plans/{feature_plan_id}/execute

Routes must stay thin. No pandas in routes.

Tests:

* feature plan route works
* decision validation blocks missing approval
* execute route creates FeatureResult
* execute route creates enriched DatasetVersion
* previous DatasetVersion unchanged

---

## M6D: Frontend for Suggested Metrics

Goal: add a minimal beginner-friendly frontend flow for reviewing suggested metrics, approving/skipping them, validating decisions, and applying selected metrics.

Frontend only. Do not change backend logic.

Use existing M6C endpoints:

- `POST /datasets/{dataset_id}/versions/{dataset_version_id}/feature-plans`
- `POST /feature-plans/{feature_plan_id}/decisions/validate`
- `POST /feature-plans/{feature_plan_id}/execute`

User-facing language:

Use:
- Suggested metrics
- Calculated metrics
- Useful breakdowns
- Needs your review
- Apply selected metrics
- New enriched copy created
- Previous data unchanged

Avoid showing:
- FeaturePlanJson
- operation_type
- DatasetVersion
- FeatureResult
- execution_log_json
- artifact
- schema
- metadata

UI should show each suggestion with:
- metric name
- plain-English formula
- why it helps
- required columns
- Approve / Skip controls
- optional Show details

Behavior:
1. Load or create a feature plan.
2. Show suggested metrics/features.
3. Let user approve or skip each suggestion.
4. Validate decisions before execution.
5. If validation passes, execute approved features.
6. Show success state:
   - selected metrics were added
   - a new enriched copy was created
   - previous data was not overwritten

Decision behavior:
- send explicit decisions for all features if possible
- approved features execute
- rejected features skip
- do not execute if validation fails

Do not implement:
- custom formula builder
- arbitrary code execution
- charts
- insights
- backend logic
- database changes
- authentication
- polished dashboard UI

Acceptance criteria:
- user can view suggested metrics
- user can approve/skip suggestions
- frontend validates decisions before execution
- frontend applies approved metrics
- UI uses beginner-friendly language
- UI does not expose internal backend terms by default