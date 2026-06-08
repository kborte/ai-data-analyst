# Milestone 8: Visualization Generation

## Goal

Generate simple, deterministic chart suggestions and chart specs from a dataset version.

No LLM calls. No insight generation. No dashboard builder. No advanced frontend editing.

Use this model:

VisualizationPlan = proposed charts
VisualizationDecisions = user approvals/rejections
VisualizationResult = generated chart specs
DatasetVersion = unchanged input data

Do not mutate dataset versions.

---

## M8A: Chart Schemas + Chart Planner

Implement visualization schemas if missing or broken.

Use broad chart types only:

* bar
* line
* pie
* scatter

Planner input:

* DataProfile
* optional DatasetVersion metadata
* optional user goal if already available

Planner output:

* chart suggestions

Suggest only obvious charts:

* line chart for date + numeric metric
* bar chart for category + numeric metric
* bar chart for top categories by count
* pie chart only for small part-to-whole breakdowns
* scatter plot for two numeric columns
* grouped bar only if simple

Max suggestions: 8.

Every chart suggestion must require approval.

Each chart suggestion should include:

* visualization_id
* title
* description
* chart_type
* input_table
* x_column
* y_column or y_columns
* group_by, if needed
* aggregation, if needed
* filters, if needed
* sort, if needed
* limit, if needed
* user_facing_explanation
* requires_human_approval

Tests:

* date + revenue suggests line chart
* category + revenue suggests bar chart
* category count suggests bar chart
* two numeric columns suggest scatter chart
* pie chart is only suggested for low-cardinality categories
* max suggestions respected
* all suggestions require approval

---

## M8B: Chart Spec Executor

Implement deterministic chart spec generation.

Input:

* dict of table_name -> pandas DataFrame
* approved visualization definitions

Output:

* chart specs
* chart data
* execution results

Supported chart specs:

* bar
* line
* pie
* scatter

Rules:

* never mutate input DataFrames
* no arbitrary Python
* validate required columns exist
* aggregate data if chart definition asks for aggregation
* sort/limit safely
* return failed result for missing columns
* keep chart data small enough for frontend rendering
* no image generation
* no LLM-written insights

Chart spec should be frontend-friendly JSON.

Recommended shape:

```json
{
  "visualization_id": "viz_001_revenue_over_time",
  "title": "Revenue over time",
  "chart_type": "line",
  "x_key": "date",
  "series": [
    {
      "data_key": "revenue",
      "label": "Revenue"
    }
  ],
  "data": [
    {
      "date": "2026-01-01",
      "revenue": 1200
    }
  ],
  "description": "Shows how revenue changed over time."
}
```

Tests:

* line chart spec generated from date + revenue
* bar chart spec generated from category + revenue
* scatter chart spec generated from two numeric columns
* pie chart spec generated for low-cardinality category share
* missing column returns failed result
* input DataFrame is not mutated

---

## M8C: Visualization Service + API

Implement visualization service and thin API routes.

Service should:

1. create visualization plan from profile
2. validate decisions
3. generate approved chart specs
4. save VisualizationPlan
5. save VisualizationResult
6. leave dataset version unchanged

Routes:

POST /datasets/{dataset_id}/versions/{dataset_version_id}/visualization-plans

POST /visualization-plans/{visualization_plan_id}/decisions/validate

POST /visualization-plans/{visualization_plan_id}/generate

Routes must stay thin. No pandas in routes.

Approval rules:

* generate only approved charts
* skip rejected charts
* block generation if any chart requiring approval has no decision
* do not mutate VisualizationPlan

Tests:

* visualization plan route works
* decision validation blocks missing approval
* generate route creates VisualizationResult
* generated result includes chart specs
* dataset version is unchanged

---

## M8D: Minimal Frontend Chart Preview

Frontend only.

Add a minimal beginner-friendly UI for reviewing suggested charts and rendering generated chart specs.

Use existing M8C endpoints.

User-facing language:

Use:

* Suggested charts
* Preview chart
* Create selected charts
* Why this chart helps
* Data used
* Previous data unchanged

Avoid:

* VisualizationPlanJson
* chart_spec_json
* operation_type
* artifact
* schema
* metadata

Behavior:

1. Load or create visualization plan.
2. Show suggested charts.
3. Let user approve or skip charts.
4. Validate decisions.
5. Generate approved chart specs.
6. Render generated charts if chart renderer exists.
7. If no renderer exists, show chart spec summaries in cards.

Do not implement:

* dashboard builder
* drag-and-drop charts
* custom chart editor
* LLM insights
* backend logic
* database changes

Acceptance criteria:

* user can view suggested charts
* user can approve/skip charts
* frontend validates before generation
* frontend generates selected charts
* UI avoids backend terms by default
