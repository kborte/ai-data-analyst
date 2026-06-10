export interface Dataset {
  dataset_id: string;
  workspace_id: string;
  name: string;
  created_at: string;
}

export interface DatasetVersion {
  dataset_version_id: string;
  dataset_id: string;
  version_number: number;
  version_type: string;
  display_name: string | null;
  description: string | null;
  storage_path: string | null;
  row_count: number | null;
  column_count: number | null;
  created_at: string;
  parent_version_id: string | null;
}

export interface DatasetTable {
  table_id: string;
  dataset_version_id: string;
  table_name: string;
  storage_path: string | null;
  row_count: number | null;
  column_count: number | null;
}

export interface ColumnProfile {
  column_name: string;
  data_type: string;
  null_count: number | null;
  null_percent: number | null;
  unique_count: number | null;
  is_likely_id: boolean;
  is_likely_metric: boolean;
  is_likely_categorical: boolean;
  is_likely_date: boolean;
}

export interface DataProfile {
  profile_id: string;
  dataset_version_id: string;
  table_name: string;
  row_count: number | null;
  column_count: number | null;
  column_profiles: ColumnProfile[];
  created_at: string;
}

export interface SavedViewPreview {
  saved_view_id: string;
  columns: string[];
  rows: string[][];
  preview_row_count: number;
  total_rows_in_artifact: number | null;
}

export interface SavedView {
  saved_view_id: string;
  workspace_id: string;
  dataset_id: string;
  dataset_version_id: string;
  name: string;
  description: string | null;
  source_type: string;
  storage_path: string | null;
  storage_format: string | null;
  row_count: number | null;
  column_count: number | null;
  created_at: string;
}

export interface SavedVisual {
  visual_id: string;
  workspace_id: string;
  dataset_id: string;
  dataset_version_id: string;
  title: string;
  description: string | null;
  chart_type: string;
  source_type: string;
  created_at: string;
}

export interface DatasetFile {
  file_id: string;
  data_source_id: string;
  original_filename: string;
  file_kind: string;
  size_bytes: number;
  uploaded_at: string;
}

export interface Job {
  job_id: string;
  workspace_id: string;
  dataset_id: string | null;
  job_type: string;
  status: string;
  created_at: string;
}

export interface TextOutput {
  output_type: "text";
  dataset_version_id: string;
  title: string;
  content: string;
  references: string[];
}

export interface TableOutput {
  output_type: "table";
  dataset_version_id: string;
  title: string;
  description: string | null;
  columns: string[];
  preview_rows: unknown[][];
  row_count: number;
  source_spec_json: Record<string, unknown>;
  storage_backend: string | null;
  storage_bucket: string | null;
  storage_path: string | null;
  storage_format: string | null;
  can_save_as_view: true;
}

export interface VisualOutput {
  output_type: "visual";
  dataset_version_id: string;
  title: string;
  description: string | null;
  chart_type: string;
  chart_spec_json: Record<string, unknown>;
  source_spec_json: Record<string, unknown>;
  data_storage_backend: string | null;
  data_storage_bucket: string | null;
  data_storage_path: string | null;
  can_save_to_visuals: true;
}

export interface MixedOutput {
  output_type: "mixed";
  dataset_version_id: string;
  title: string;
  summary: string;
  outputs: (TextOutput | TableOutput | VisualOutput)[];
}

export type AnalyticsOutput = TextOutput | TableOutput | VisualOutput | MixedOutput;

export interface AnalyticsResponse {
  dataset_id: string;
  dataset_version_id: string;
  question: string;
  output: AnalyticsOutput;
}

// ---------------------------------------------------------------------------
// Cleaning plan
// ---------------------------------------------------------------------------

export interface CleaningIssue {
  issue_type: string;
  table_name: string;
  column_name: string | null;
  description: string;
  affected_rows_count: number;
  affected_rows_percent: number;
}

export interface CleaningRecommendation {
  action_type: string;
  recommended_action: string;
  rationale: string;
  impact_level: string;
  affects_key_metrics: boolean;
  requires_human_approval: boolean;
  default_decision: string;
}

export interface CleaningStep {
  step_id: string;
  sequence_order: number;
  issue: CleaningIssue;
  recommendation: CleaningRecommendation;
}

export interface CleaningPlan {
  cleaning_plan_id: string;
  dataset_version_id: string;
  status: string;
  plan_json: {
    steps: CleaningStep[];
    summary?: {
      total_steps: number;
      steps_requiring_approval: number;
    };
  };
  created_at: string;
}

// ---------------------------------------------------------------------------
// Feature plan
// ---------------------------------------------------------------------------

export interface FeatureDefinition {
  feature_id: string;
  feature_name: string;
  display_name: string;
  description: string;
  operation_type: string;
  formula_display: string;
  requires_human_approval: boolean;
}

export interface FeaturePlan {
  feature_plan_id: string;
  dataset_version_id: string;
  status: string;
  plan_json: {
    features: FeatureDefinition[];
  };
  created_at: string;
}

// ---------------------------------------------------------------------------
// Workflow orchestrator
// ---------------------------------------------------------------------------

export interface ApprovalItem {
  id: string;
  title: string;
  description: string;
  recommended_action: string;
  details: string | null;
  default_decision: string;
}

export interface WorkflowState {
  workspace_id: string | null;
  dataset_id: string;
  dataset_version_id: string;
  question: string;
  stage: string;
  intent: string;
  profile_id: string | null;
  cleaning_plan_id: string | null;
  feature_plan_id: string | null;
  resolved_version_id: string | null;
}

export interface NeedsApprovalResponse {
  response_type: "needs_approval";
  stage: string;
  message: string;
  dataset_id: string;
  dataset_version_id: string;
  items: ApprovalItem[];
  workflow_state: WorkflowState;
}

export interface NeedsClarificationResponse {
  response_type: "needs_clarification";
  message: string;
  dataset_id: string;
  dataset_version_id: string;
  options: string[];
}

export interface AnalysisResultResponse {
  response_type: "analysis_result";
  dataset_id: string;
  dataset_version_id: string;
  summary_text: string;
  outputs: AnalyticsOutput[];
  assumptions_used: string[];
}

export type WorkflowResponse =
  | NeedsApprovalResponse
  | NeedsClarificationResponse
  | AnalysisResultResponse;
