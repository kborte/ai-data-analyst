import type {
  AnalyticsResponse,
  CleaningPlan,
  Dataset,
  DatasetFile,
  DatasetVersion,
  DatasetTable,
  DataProfile,
  FeaturePlan,
  SavedView,
  SavedViewPreview,
  SavedVisual,
  Job,
  WorkflowResponse,
} from "./types";

export interface ApiUser {
  user_id: string;
  username: string;
}

export interface ApiWorkspace {
  workspace_id: string;
  name: string;
  created_by_user_id: string;
  created_at: string;
}

async function del(path: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE", cache: "no-store" });
  if (!res.ok && res.status !== 204) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`DELETE ${path} → ${res.status}: ${text}`);
  }
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`GET ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`POST ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export async function apiLogin(username: string): Promise<ApiUser> {
  return post<ApiUser>("/auth/login", { username });
}

// ── Workspaces ───────────────────────────────────────────────────────────────

export async function apiCreateWorkspace(name: string, createdByUserId: string): Promise<ApiWorkspace> {
  return post<ApiWorkspace>("/workspaces", { name, created_by_user_id: createdByUserId });
}

export async function apiListUserWorkspaces(userId: string): Promise<ApiWorkspace[]> {
  return get<ApiWorkspace[]>(`/users/${userId}/workspaces`);
}

export async function apiGetWorkspace(workspaceId: string): Promise<ApiWorkspace> {
  return get<ApiWorkspace>(`/workspaces/${workspaceId}`);
}

export async function apiAddWorkspaceMember(workspaceId: string, username: string): Promise<void> {
  const res = await fetch(`${API_BASE}/workspaces/${workspaceId}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
    cache: "no-store",
  });
  if (!res.ok && res.status !== 204) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`Add member → ${res.status}: ${text}`);
  }
}

export async function apiLookupUser(username: string): Promise<ApiUser> {
  return get<ApiUser>(`/users?username=${encodeURIComponent(username)}`);
}

// ── Datasets ─────────────────────────────────────────────────────────────────

export async function createDataset(workspaceId: string, name: string): Promise<Dataset> {
  return post(`/workspaces/${workspaceId}/datasets`, { name });
}

export async function listDatasets(workspaceId: string): Promise<Dataset[]> {
  return get(`/workspaces/${workspaceId}/datasets`);
}

export async function listDatasetFiles(datasetId: string): Promise<DatasetFile[]> {
  return get(`/datasets/${datasetId}/files`);
}

export async function removeDatasetFile(datasetId: string, fileId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/datasets/${datasetId}/files/${fileId}`,
    { method: "DELETE", cache: "no-store" }
  );
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`DELETE file → ${res.status}: ${text}`);
  }
}

export async function uploadFileToDataset(
  workspaceId: string,
  datasetId: string,
  file: File
): Promise<Job> {
  const form = new FormData();
  form.append("file", file);
  form.append("dataset_id", datasetId);
  const res = await fetch(
    `${API_BASE}/workspaces/${workspaceId}/datasets/upload`,
    { method: "POST", body: form }
  );
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`Upload failed: ${text}`);
  }
  return res.json() as Promise<Job>;
}

export async function getDataset(datasetId: string): Promise<Dataset> {
  return get(`/datasets/${datasetId}`);
}

export async function listVersions(datasetId: string): Promise<DatasetVersion[]> {
  return get(`/datasets/${datasetId}/versions`);
}

export async function listTables(
  datasetId: string,
  versionId: string
): Promise<DatasetTable[]> {
  return get(`/datasets/${datasetId}/versions/${versionId}/tables`);
}

export async function listProfiles(
  datasetId: string,
  versionId: string
): Promise<DataProfile[]> {
  return get(`/datasets/${datasetId}/versions/${versionId}/profiles`);
}

export async function listViews(
  datasetId: string,
  versionId: string
): Promise<SavedView[]> {
  return get(`/datasets/${datasetId}/versions/${versionId}/views`);
}

export async function previewView(viewId: string): Promise<SavedViewPreview> {
  return get(`/views/${viewId}/preview`);
}

export function downloadViewUrl(viewId: string): string {
  return `${API_BASE}/views/${viewId}/download?format=csv`;
}

export async function deleteView(viewId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/views/${viewId}`, {
    method: "DELETE",
    cache: "no-store",
  });
  if (!res.ok && res.status !== 204) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`DELETE /views/${viewId} → ${res.status}: ${text}`);
  }
}

export async function listVisuals(
  datasetId: string,
  versionId: string
): Promise<SavedVisual[]> {
  return get(`/datasets/${datasetId}/versions/${versionId}/visuals`);
}

export async function getJob(jobId: string): Promise<Job> {
  return get(`/jobs/${jobId}`);
}

export async function uploadDataset(
  workspaceId: string,
  file: File
): Promise<Job> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(
    `${API_BASE}/workspaces/${workspaceId}/datasets/upload`,
    { method: "POST", body: form }
  );
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`Upload failed: ${text}`);
  }
  return res.json() as Promise<Job>;
}

export async function analyticsAsk(
  datasetId: string,
  versionId: string,
  question: string
): Promise<AnalyticsResponse> {
  return post(
    `/datasets/${datasetId}/versions/${versionId}/analytics/ask`,
    { question, recent_messages: [], prior_output_refs: [] }
  );
}

export async function analyticsWorkflow(
  datasetId: string,
  versionId: string,
  question: string,
  workflowState?: unknown,
  cleaningDecisions?: unknown[],
  featureDecisions?: unknown[]
): Promise<WorkflowResponse> {
  return post(
    `/datasets/${datasetId}/versions/${versionId}/analytics/workflow`,
    {
      question,
      workflow_state: workflowState ?? null,
      cleaning_decisions: cleaningDecisions ?? [],
      feature_decisions: featureDecisions ?? [],
    }
  );
}

export async function saveTableAsView(payload: {
  dataset_id: string;
  dataset_version_id: string;
  name: string;
  description?: string;
  columns: string[];
  rows: unknown[][];
}): Promise<SavedView> {
  return post("/analytics/table-results/save-as-view", payload);
}

export async function saveVisualToVisuals(payload: {
  dataset_id: string;
  dataset_version_id: string;
  title: string;
  description?: string;
  chart_type: string;
  chart_spec_json: Record<string, unknown>;
}): Promise<SavedVisual> {
  return post("/analytics/visual-results/save-as-visual", payload);
}

// ── Cleaning ─────────────────────────────────────────────────────────────────

export async function createCleaningPlan(
  datasetId: string,
  versionId: string,
  profileId: string
): Promise<CleaningPlan> {
  return post(`/datasets/${datasetId}/versions/${versionId}/cleaning-plans`, {
    profile_id: profileId,
  });
}

export interface CleaningDecisionItem {
  step_id: string;
  decision: "approve" | "reject";
}

export async function executeCleaningPlan(
  planId: string,
  payload: {
    workspace_id: string;
    dataset_id: string;
    input_dataset_version_id: string;
    executed_by_user_id: string;
    decisions: CleaningDecisionItem[];
  }
): Promise<Job> {
  return post(`/cleaning-plans/${planId}/execute`, payload);
}

// ── Features ─────────────────────────────────────────────────────────────────

export async function createFeaturePlan(
  datasetId: string,
  versionId: string,
  profileId: string
): Promise<FeaturePlan> {
  return post(`/datasets/${datasetId}/versions/${versionId}/feature-plans`, {
    profile_id: profileId,
  });
}

export interface FeatureDecisionItem {
  feature_id: string;
  decision: "approve" | "reject";
}

export async function executeFeaturePlan(
  planId: string,
  payload: {
    workspace_id: string;
    dataset_id: string;
    input_dataset_version_id: string;
    executed_by_user_id: string;
    decisions: FeatureDecisionItem[];
  }
): Promise<Job> {
  return post(`/feature-plans/${planId}/execute`, payload);
}

export async function pollJob(
  jobId: string,
  onDone: () => void,
  onError: (msg: string) => void,
  timeoutMs = 120_000
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  const interval = setInterval(async () => {
    if (Date.now() > deadline) {
      clearInterval(interval);
      onError("Timed out waiting for job to complete. Is the worker running?");
      return;
    }
    try {
      const job = await getJob(jobId);
      if (job.status === "completed") {
        clearInterval(interval);
        onDone();
      } else if (job.status === "failed" || job.status === "cancelled") {
        clearInterval(interval);
        onError(`Job ${job.status}`);
      }
    } catch {
      clearInterval(interval);
      onError("Could not poll job status");
    }
  }, 2000);
}
