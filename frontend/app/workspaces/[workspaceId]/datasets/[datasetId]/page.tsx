"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  analyticsAsk,
  createCleaningPlan,
  createFeaturePlan,
  executeCleaningPlan,
  executeFeaturePlan,
  getDataset,
  listVersions,
  listTables,
  listProfiles,
  listViews,
  listVisuals,
  listDatasetFiles,
  removeDatasetFile,
  saveTableAsView,
  saveVisualToVisuals,
  uploadFileToDataset,
  pollJob,
} from "@/lib/api";
import type {
  AnalyticsOutput,
  CleaningPlan,
  Dataset,
  DatasetFile,
  DatasetVersion,
  DatasetTable,
  DataProfile,
  FeaturePlan,
  SavedView,
  SavedVisual,
  TableOutput,
  VisualOutput,
} from "@/lib/types";
import { getCurrentUser } from "@/lib/store";

type Tab = "chat" | "views" | "visuals" | "tables" | "versions";

const TABS: { key: Tab; label: string }[] = [
  { key: "chat", label: "Chat" },
  { key: "views", label: "Saved views" },
  { key: "visuals", label: "Saved visuals" },
  { key: "tables", label: "Tables" },
  { key: "versions", label: "Versions" },
];

function versionLabel(v: DatasetVersion): string {
  if (v.display_name) return v.display_name;
  switch (v.version_type) {
    case "original": return "Original upload";
    case "cleaned": return "Cleaned copy";
    case "enriched": return "Copy with calculated metrics";
    default: return `Version ${v.version_number}`;
  }
}

export default function DatasetPage() {
  const { workspaceId, datasetId } = useParams<{
    workspaceId: string;
    datasetId: string;
  }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = (searchParams.get("tab") as Tab | null) ?? "chat";

  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [versions, setVersions] = useState<DatasetVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);

  const [tables, setTables] = useState<DatasetTable[]>([]);
  const [profiles, setProfiles] = useState<DataProfile[]>([]);
  const [views, setViews] = useState<SavedView[]>([]);
  const [visuals, setVisuals] = useState<SavedVisual[]>([]);

  const [loadingMeta, setLoadingMeta] = useState(true);
  const [loadingTab, setLoadingTab] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function init() {
      setLoadingMeta(true);
      setError(null);
      try {
        const [ds, vers] = await Promise.all([
          getDataset(datasetId),
          listVersions(datasetId),
        ]);
        setDataset(ds);
        setVersions(vers);
        if (vers.length > 0) {
          setSelectedVersionId(vers[vers.length - 1].dataset_version_id);
        }
      } catch (e) {
        setError(String(e));
      } finally {
        setLoadingMeta(false);
      }
    }
    init();
  }, [datasetId]);

  useEffect(() => {
    if (!selectedVersionId) return;
    setLoadingTab(true);
    setError(null);

    const loaders: Record<Tab, () => Promise<void>> = {
      chat: async () => {},
      tables: async () => {
        const [t, p] = await Promise.all([
          listTables(datasetId, selectedVersionId),
          listProfiles(datasetId, selectedVersionId),
        ]);
        setTables(t);
        setProfiles(p);
      },
      versions: async () => {},
      views: async () => {
        setViews(await listViews(datasetId, selectedVersionId));
      },
      visuals: async () => {
        setVisuals(await listVisuals(datasetId, selectedVersionId));
      },
    };

    loaders[tab]()
      .catch((e) => setError(String(e)))
      .finally(() => setLoadingTab(false));
  }, [tab, selectedVersionId, datasetId]);

  function setTab(t: Tab) {
    router.push(
      `/workspaces/${workspaceId}/datasets/${datasetId}?tab=${t}`
    );
  }

  const selectedVersion = versions.find(
    (v) => v.dataset_version_id === selectedVersionId
  );

  return (
    <main className="min-h-screen bg-gray-50">
      <nav className="border-b border-gray-200 bg-white px-6 py-3 flex items-center gap-3 text-sm text-gray-500">
        <button onClick={() => router.push("/workspaces")} className="hover:text-gray-800">
          Workspaces
        </button>
        <span>/</span>
        <button
          onClick={() => router.push(`/workspaces/${workspaceId}`)}
          className="hover:text-gray-800"
        >
          {workspaceId.slice(0, 8)}…
        </button>
        <span>/</span>
        <span className="text-gray-800 font-medium truncate max-w-xs">
          {dataset?.name ?? datasetId}
        </span>
      </nav>

      {loadingMeta && (
        <p className="text-sm text-gray-400 px-6 py-10">Loading dataset…</p>
      )}
      {error && (
        <p className="text-sm text-red-500 px-6 py-4">{error}</p>
      )}

      {!loadingMeta && dataset && (
        <div className="max-w-5xl mx-auto px-6 py-8 space-y-4">
          {/* Header row */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{dataset.name}</h1>
              {selectedVersion && (
                <p className="text-xs text-gray-400 mt-0.5">
                  {selectedVersion.row_count != null && `${selectedVersion.row_count.toLocaleString()} rows · `}
                  {selectedVersion.column_count != null && `${selectedVersion.column_count} columns · `}
                  Created {new Date(dataset.created_at).toLocaleDateString()}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-gray-600 shrink-0">Version</label>
              <select
                value={selectedVersionId ?? ""}
                onChange={(e) => setSelectedVersionId(e.target.value)}
                className="border border-gray-300 rounded-lg text-sm px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500 max-w-xs"
              >
                {versions.length === 0 && <option value="">No versions yet</option>}
                {versions.map((v, i) => (
                  <option key={v.dataset_version_id} value={v.dataset_version_id}>
                    {i === versions.length - 1 ? "Current — " : ""}{versionLabel(v)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Collapsible files section */}
          <FilesPanel datasetId={datasetId} workspaceId={workspaceId} collapsible />

          {/* Tabs */}
          <div className="border-b border-gray-200 flex gap-1">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  tab === t.key
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-gray-500 hover:text-gray-700"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="min-h-48">
            {loadingTab && <p className="text-sm text-gray-400">Loading…</p>}
            {tab === "chat" && selectedVersionId && (
              <ChatPanel datasetId={datasetId} versionId={selectedVersionId} workspaceId={workspaceId} />
            )}
            {tab === "chat" && !selectedVersionId && (
              <p className="text-sm text-gray-400">Upload a file first to start chatting.</p>
            )}
            {!loadingTab && tab === "views" && <ViewsPanel views={views} />}
            {!loadingTab && tab === "visuals" && <VisualsPanel visuals={visuals} />}
            {!loadingTab && tab === "tables" && (
              <TablesPanel tables={tables} profiles={profiles} />
            )}
            {!loadingTab && tab === "versions" && (
              <VersionsPanel versions={versions} selectedVersionId={selectedVersionId} />
            )}
          </div>
        </div>
      )}
    </main>
  );
}

function FilesPanel({
  datasetId,
  workspaceId,
  collapsible = false,
}: {
  datasetId: string;
  workspaceId: string;
  collapsible?: boolean;
}) {
  const [open, setOpen] = useState(!collapsible);
  const [files, setFiles] = useState<DatasetFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setFiles(await listDatasetFiles(datasetId));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [datasetId]);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadStatus("Uploading…");
    try {
      const job = await uploadFileToDataset(workspaceId, datasetId, file);
      setUploadStatus("Processing…");
      await pollJob(
        job.job_id,
        () => {
          setUploadStatus("Done!");
          setUploading(false);
          if (fileRef.current) fileRef.current.value = "";
          load();
        },
        (msg) => {
          setUploadStatus(`Failed: ${msg}`);
          setUploading(false);
        }
      );
    } catch (e) {
      setUploadStatus(`Error: ${String(e)}`);
      setUploading(false);
    }
  }

  async function handleRemove(fileId: string) {
    try {
      await removeDatasetFile(datasetId, fileId);
      setFiles((prev) => prev.filter((f) => f.file_id !== fileId));
    } catch (e) {
      setError(String(e));
    }
  }

  function fmt(bytes: number) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  const fileCount = files.length;

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <button
        onClick={() => collapsible && setOpen((v) => !v)}
        className={`w-full flex items-center justify-between px-5 py-3 text-sm font-medium text-gray-700 ${collapsible ? "hover:bg-gray-50 cursor-pointer" : "cursor-default"}`}
      >
        <span>
          Files
          {!loading && (
            <span className="ml-2 text-xs font-normal text-gray-400">
              {fileCount === 0 ? "— upload CSV or Excel to get started" : `${fileCount} file${fileCount !== 1 ? "s" : ""}`}
            </span>
          )}
        </span>
        {collapsible && (
          <span className="text-gray-400 text-xs">{open ? "▲ Hide" : "▼ Show"}</span>
        )}
      </button>

      {open && (
        <div className="px-5 pb-4 space-y-3 border-t border-gray-100">
          <form onSubmit={handleUpload} className="flex items-center gap-3 flex-wrap pt-3">
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              className="text-sm text-gray-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
            <button
              type="submit"
              disabled={uploading}
              className="bg-blue-600 text-white text-sm font-medium px-4 py-1.5 rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {uploading ? "Uploading…" : "Add file"}
            </button>
            {uploadStatus && <span className="text-xs text-gray-500">{uploadStatus}</span>}
          </form>

          {error && <p className="text-xs text-red-500">{error}</p>}
          {loading && <p className="text-xs text-gray-400">Loading…</p>}
          {!loading && files.length === 0 && (
            <p className="text-xs text-gray-400">No files yet. Supported formats: CSV, Excel (.xlsx, .xls).</p>
          )}

          {files.length > 0 && (
            <ul className="space-y-1.5">
              {files.map((f) => (
                <li
                  key={f.file_id}
                  className="flex items-center justify-between gap-4 py-1.5"
                >
                  <div>
                    <p className="text-sm text-gray-800">{f.original_filename}</p>
                    <p className="text-xs text-gray-400">
                      {fmt(f.size_bytes)} · {f.file_kind.toUpperCase()} ·{" "}
                      {new Date(f.uploaded_at).toLocaleDateString()}
                    </p>
                  </div>
                  <button
                    onClick={() => handleRemove(f.file_id)}
                    className="text-xs text-red-400 hover:text-red-600 shrink-0"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function TablesPanel({
  tables,
  profiles,
}: {
  tables: DatasetTable[];
  profiles: DataProfile[];
}) {
  const profileMap = Object.fromEntries(
    profiles.map((p) => [p.table_name, p])
  );

  if (tables.length === 0) {
    return <p className="text-sm text-gray-400">No tables in this copy.</p>;
  }

  return (
    <div className="space-y-6">
      {tables.map((t) => {
        const prof = profileMap[t.table_name];
        return (
          <div key={t.table_id} className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
              <p className="text-sm font-semibold text-gray-800">{t.table_name}</p>
              <span className="text-xs text-gray-400">
                {t.row_count != null ? `${t.row_count.toLocaleString()} rows` : ""}
                {t.row_count != null && t.column_count != null ? " · " : ""}
                {t.column_count != null ? `${t.column_count} columns` : ""}
              </span>
            </div>

            {prof ? (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50 text-gray-500">
                      <th className="text-left px-4 py-2 font-medium">Column</th>
                      <th className="text-left px-4 py-2 font-medium">Type</th>
                      <th className="text-right px-4 py-2 font-medium">Nulls</th>
                      <th className="text-right px-4 py-2 font-medium">Unique</th>
                      <th className="px-4 py-2 font-medium text-center">Tags</th>
                    </tr>
                  </thead>
                  <tbody>
                    {prof.column_profiles.map((col) => (
                      <tr
                        key={col.column_name}
                        className="border-b border-gray-50 hover:bg-gray-50"
                      >
                        <td className="px-4 py-2 font-mono text-gray-800">{col.column_name}</td>
                        <td className="px-4 py-2 text-gray-500">{col.data_type}</td>
                        <td className="px-4 py-2 text-right text-gray-500">
                          {col.null_percent != null
                            ? `${col.null_percent.toFixed(1)}%`
                            : "—"}
                        </td>
                        <td className="px-4 py-2 text-right text-gray-500">
                          {col.unique_count?.toLocaleString() ?? "—"}
                        </td>
                        <td className="px-4 py-2 text-center">
                          <span className="flex gap-1 flex-wrap justify-center">
                            {col.is_likely_id && <Tag label="ID" color="purple" />}
                            {col.is_likely_metric && <Tag label="metric" color="green" />}
                            {col.is_likely_date && <Tag label="date" color="blue" />}
                            {col.is_likely_categorical && <Tag label="category" color="orange" />}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-gray-400 px-5 py-3">No profile available for this table.</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Tag({
  label,
  color,
}: {
  label: string;
  color: "purple" | "green" | "blue" | "orange";
}) {
  const styles: Record<string, string> = {
    purple: "bg-purple-50 text-purple-700",
    green: "bg-green-50 text-green-700",
    blue: "bg-blue-50 text-blue-700",
    orange: "bg-orange-50 text-orange-700",
  };
  return (
    <span
      className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${styles[color]}`}
    >
      {label}
    </span>
  );
}

function VersionsPanel({
  versions,
  selectedVersionId,
}: {
  versions: DatasetVersion[];
  selectedVersionId: string | null;
}) {
  if (versions.length === 0) {
    return <p className="text-sm text-gray-400">No versions yet.</p>;
  }

  return (
    <ul className="space-y-2">
      {[...versions].reverse().map((v, i) => {
        const isCurrent = v.dataset_version_id === selectedVersionId;
        const isLatest = i === 0;
        return (
          <li
            key={v.dataset_version_id}
            className={`bg-white border rounded-xl px-5 py-4 flex items-start justify-between gap-4 ${
              isCurrent ? "border-blue-400 ring-1 ring-blue-200" : "border-gray-200"
            }`}
          >
            <div>
              <p className="text-sm font-semibold text-gray-800">
                {versionLabel(v)}
                {isLatest && (
                  <span className="ml-2 text-xs font-medium text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded">
                    Current copy
                  </span>
                )}
              </p>
              {v.description && (
                <p className="text-xs text-gray-400 mt-0.5">{v.description}</p>
              )}
              <p className="text-xs text-gray-400 mt-1">
                {new Date(v.created_at).toLocaleString()}
              </p>
            </div>
            <div className="text-right shrink-0 text-xs text-gray-400 space-y-0.5">
              {v.row_count != null && (
                <p>{v.row_count.toLocaleString()} rows</p>
              )}
              {v.column_count != null && <p>{v.column_count} cols</p>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function ViewsPanel({ views }: { views: SavedView[] }) {
  if (views.length === 0) {
    return <p className="text-sm text-gray-400">No saved views for this copy yet.</p>;
  }

  return (
    <ul className="space-y-2">
      {views.map((v) => (
        <li
          key={v.saved_view_id}
          className="bg-white border border-gray-200 rounded-xl px-5 py-4"
        >
          <p className="text-sm font-semibold text-gray-800">{v.name}</p>
          {v.description && (
            <p className="text-xs text-gray-400 mt-0.5">{v.description}</p>
          )}
          <div className="flex gap-4 mt-2 text-xs text-gray-400">
            {v.row_count != null && <span>{v.row_count.toLocaleString()} rows</span>}
            {v.column_count != null && <span>{v.column_count} cols</span>}
            {v.storage_format && <span>{v.storage_format.toUpperCase()}</span>}
            <span>{new Date(v.created_at).toLocaleDateString()}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

function VisualsPanel({ visuals }: { visuals: SavedVisual[] }) {
  if (visuals.length === 0) {
    return <p className="text-sm text-gray-400">No saved visuals for this copy yet.</p>;
  }

  return (
    <ul className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {visuals.map((v) => (
        <li
          key={v.visual_id}
          className="bg-white border border-gray-200 rounded-xl px-5 py-4"
        >
          <p className="text-sm font-semibold text-gray-800">{v.title}</p>
          {v.description && (
            <p className="text-xs text-gray-400 mt-0.5">{v.description}</p>
          )}
          <div className="flex gap-3 mt-2 text-xs text-gray-400">
            <span className="capitalize">{v.chart_type} chart</span>
            <span>{new Date(v.created_at).toLocaleDateString()}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Chat — types and intent detection
// ---------------------------------------------------------------------------

type ChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; kind: "analytics"; output: AnalyticsOutput }
  | { id: string; role: "assistant"; kind: "cleaning-plan"; plan: CleaningPlan; datasetId: string; versionId: string; workspaceId: string; userId: string }
  | { id: string; role: "assistant"; kind: "feature-plan"; plan: FeaturePlan; datasetId: string; versionId: string; workspaceId: string; userId: string }
  | { id: string; role: "assistant"; kind: "text"; text: string }
  | { id: string; role: "assistant"; kind: "error"; text: string };

const _CLEANING_KEYWORDS = [
  "clean", "fix data", "fix missing", "handle null", "remove duplicate",
  "deduplic", "data quality", "improve data", "inconsistenc", "quality issue",
  "data issue", "missing value", "null value", "fix null", "tidy",
];
const _FEATURE_KEYWORDS = [
  "add feature", "add column", "add metric", "new column",
  "feature engineer", "derived column", "create metric",
  "calculate column", "add kpi",
];

function detectChatIntent(q: string): "cleaning" | "feature" | "analytics" {
  const lower = q.toLowerCase();
  if (_CLEANING_KEYWORDS.some((k) => lower.includes(k))) return "cleaning";
  if (_FEATURE_KEYWORDS.some((k) => lower.includes(k))) return "feature";
  return "analytics";
}

// ---------------------------------------------------------------------------
// ChatPanel
// ---------------------------------------------------------------------------

function ChatPanel({
  datasetId,
  versionId,
  workspaceId,
}: {
  datasetId: string;
  versionId: string;
  workspaceId: string;
}) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  function push(msg: ChatMessage) {
    setMessages((prev) => [...prev, msg]);
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function ask() {
    const q = question.trim();
    if (!q || loading) return;
    setLoading(true);
    setQuestion("");
    const base = crypto.randomUUID();
    push({ id: `${base}-u`, role: "user", text: q });

    try {
      const intent = detectChatIntent(q);

      if (intent === "cleaning" || intent === "feature") {
        const profiles = await listProfiles(datasetId, versionId);
        if (profiles.length === 0) {
          push({ id: `${base}-r`, role: "assistant", kind: "text", text: "No profile found for this version. Run profiling first (click the Versions tab and choose Profile)." });
          return;
        }
        const profileId = profiles[0].profile_id;
        const user = getCurrentUser();
        const userId = user?.user_id ?? "";

        if (intent === "cleaning") {
          const plan = await createCleaningPlan(datasetId, versionId, profileId);
          if (plan.plan_json.steps.length === 0) {
            push({ id: `${base}-r`, role: "assistant", kind: "text", text: "No data quality issues found — your data looks clean!" });
          } else {
            push({ id: `${base}-r`, role: "assistant", kind: "cleaning-plan", plan, datasetId, versionId, workspaceId, userId });
          }
        } else {
          const plan = await createFeaturePlan(datasetId, versionId, profileId);
          if (plan.plan_json.features.length === 0) {
            push({ id: `${base}-r`, role: "assistant", kind: "text", text: "No additional features were suggested for this dataset." });
          } else {
            push({ id: `${base}-r`, role: "assistant", kind: "feature-plan", plan, datasetId, versionId, workspaceId, userId });
          }
        }
      } else {
        const res = await analyticsAsk(datasetId, versionId, q);
        push({ id: `${base}-r`, role: "assistant", kind: "analytics", output: res.output });
      }
    } catch (e) {
      push({ id: `${base}-e`, role: "assistant", kind: "error", text: String(e) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col" style={{ height: "620px" }}>
      <div className="flex-1 overflow-y-auto space-y-3 pb-2 pr-1">
        {messages.length === 0 && (
          <p className="text-sm text-gray-400 py-4">
            Ask a question about your data, say &quot;clean my data&quot; to review quality issues, or &quot;add features&quot; to get metric suggestions.
          </p>
        )}
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            msg={msg}
            datasetId={datasetId}
            versionId={versionId}
            onAppend={push}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="mt-3 flex gap-2 border-t border-gray-100 pt-3">
        <input
          className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Ask a question, or say 'clean my data' / 'add features'…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !loading && ask()}
          disabled={loading}
        />
        <button
          onClick={ask}
          disabled={loading || !question.trim()}
          className="bg-blue-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
        >
          {loading ? "Thinking…" : "Send"}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MessageBubble — routes each message to the right renderer
// ---------------------------------------------------------------------------

function MessageBubble({
  msg,
  datasetId,
  versionId,
  onAppend,
}: {
  msg: ChatMessage;
  datasetId: string;
  versionId: string;
  onAppend: (m: ChatMessage) => void;
}) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="bg-blue-600 text-white text-sm rounded-2xl rounded-tr-sm px-4 py-2 max-w-xl whitespace-pre-wrap">
          {msg.text}
        </div>
      </div>
    );
  }

  if (msg.kind === "text") {
    return (
      <div className="flex justify-start">
        <div className="bg-white border border-gray-200 text-sm rounded-2xl rounded-tl-sm px-4 py-3 max-w-xl text-gray-700 whitespace-pre-wrap">
          {msg.text}
        </div>
      </div>
    );
  }

  if (msg.kind === "error") {
    return (
      <div className="flex justify-start">
        <div className="bg-red-50 border border-red-200 text-sm rounded-2xl rounded-tl-sm px-4 py-3 max-w-xl text-red-700 whitespace-pre-wrap">
          {msg.text}
        </div>
      </div>
    );
  }

  if (msg.kind === "analytics") {
    return (
      <div className="w-full">
        <OutputCard output={msg.output} datasetId={datasetId} versionId={versionId} />
      </div>
    );
  }

  if (msg.kind === "cleaning-plan") {
    return (
      <div className="w-full">
        <CleaningApprovalCard
          plan={msg.plan}
          datasetId={msg.datasetId}
          versionId={msg.versionId}
          workspaceId={msg.workspaceId}
          userId={msg.userId}
          onResult={(text) =>
            onAppend({ id: crypto.randomUUID(), role: "assistant", kind: "text", text })
          }
        />
      </div>
    );
  }

  if (msg.kind === "feature-plan") {
    return (
      <div className="w-full">
        <FeatureApprovalCard
          plan={msg.plan}
          datasetId={msg.datasetId}
          versionId={msg.versionId}
          workspaceId={msg.workspaceId}
          userId={msg.userId}
          onResult={(text) =>
            onAppend({ id: crypto.randomUUID(), role: "assistant", kind: "text", text })
          }
        />
      </div>
    );
  }

  return null;
}

// ---------------------------------------------------------------------------
// CleaningApprovalCard
// ---------------------------------------------------------------------------

const _IMPACT_STYLES: Record<string, string> = {
  high: "bg-red-50 text-red-700",
  medium: "bg-orange-50 text-orange-700",
  low: "bg-green-50 text-green-700",
};

function CleaningApprovalCard({
  plan,
  datasetId,
  versionId,
  workspaceId,
  userId,
  onResult,
}: {
  plan: CleaningPlan;
  datasetId: string;
  versionId: string;
  workspaceId: string;
  userId: string;
  onResult: (text: string) => void;
}) {
  const steps = plan.plan_json.steps;
  const initialDecisions = Object.fromEntries(
    steps.map((s) => [
      s.step_id,
      (s.recommendation.default_decision === "approve" ? "approve" : "reject") as "approve" | "reject",
    ])
  );
  const [decisions, setDecisions] = useState<Record<string, "approve" | "reject">>(initialDecisions);
  const [executing, setExecuting] = useState(false);
  const [done, setDone] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  function toggle(stepId: string) {
    if (done) return;
    setDecisions((prev) => ({
      ...prev,
      [stepId]: prev[stepId] === "approve" ? "reject" : "approve",
    }));
  }

  function approveAll() {
    setDecisions(Object.fromEntries(steps.map((s) => [s.step_id, "approve"])));
  }

  function rejectAll() {
    setDecisions(Object.fromEntries(steps.map((s) => [s.step_id, "reject"])));
  }

  const approvedCount = Object.values(decisions).filter((d) => d === "approve").length;

  async function apply() {
    if (approvedCount === 0) return;
    setExecuting(true);
    setStatusMsg("Submitting…");
    try {
      const decisionItems = steps.map((s) => ({
        step_id: s.step_id,
        decision: decisions[s.step_id],
      }));
      const job = await executeCleaningPlan(plan.cleaning_plan_id, {
        workspace_id: workspaceId,
        dataset_id: datasetId,
        input_dataset_version_id: versionId,
        executed_by_user_id: userId,
        decisions: decisionItems,
      });
      setStatusMsg("Cleaning in progress…");
      await pollJob(
        job.job_id,
        () => {
          setDone(true);
          setStatusMsg(null);
          onResult(`Cleaning complete. A new cleaned copy was created. Switch to the Versions tab to see it, then select it from the version picker to analyse it.`);
        },
        (msg) => {
          setStatusMsg(null);
          setExecuting(false);
          onResult(`Cleaning failed: ${msg}`);
        }
      );
    } catch (e) {
      setStatusMsg(null);
      setExecuting(false);
      onResult(`Error running cleaning: ${String(e)}`);
    }
  }

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <p className="text-sm font-semibold text-gray-800">
            Data quality review — {steps.length} issue{steps.length !== 1 ? "s" : ""} found
          </p>
          <p className="text-xs text-gray-400 mt-0.5">
            Approve the fixes you want to apply. Rejected steps will be skipped.
          </p>
        </div>
        {!done && (
          <div className="flex gap-2 shrink-0">
            <button
              onClick={approveAll}
              className="text-xs text-green-700 bg-green-50 hover:bg-green-100 px-2.5 py-1 rounded-lg font-medium transition-colors"
            >
              Approve all
            </button>
            <button
              onClick={rejectAll}
              className="text-xs text-gray-500 bg-gray-100 hover:bg-gray-200 px-2.5 py-1 rounded-lg font-medium transition-colors"
            >
              Reject all
            </button>
          </div>
        )}
      </div>

      <ul className="divide-y divide-gray-50">
        {steps.map((step) => {
          const dec = decisions[step.step_id];
          const approved = dec === "approve";
          return (
            <li
              key={step.step_id}
              className={`px-5 py-4 flex items-start gap-4 transition-colors ${approved ? "bg-white" : "bg-gray-50 opacity-60"}`}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="text-xs font-medium text-gray-800 uppercase tracking-wide">
                    {step.issue.issue_type.replace(/_/g, " ")}
                  </span>
                  {step.issue.column_name && (
                    <span className="font-mono text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                      {step.issue.column_name}
                    </span>
                  )}
                  <span
                    className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${_IMPACT_STYLES[step.recommendation.impact_level] ?? "bg-gray-100 text-gray-600"}`}
                  >
                    {step.recommendation.impact_level} impact
                  </span>
                  {step.recommendation.requires_human_approval && (
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-yellow-50 text-yellow-700">
                      approval required
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-600">{step.issue.description}</p>
                <p className="text-xs text-gray-400 mt-0.5">
                  Fix: {step.recommendation.recommended_action}
                </p>
                {step.issue.affected_rows_percent > 0 && (
                  <p className="text-xs text-gray-400 mt-0.5">
                    Affects {step.issue.affected_rows_percent.toFixed(1)}% of rows
                  </p>
                )}
              </div>

              {!done && (
                <div className="flex gap-1.5 shrink-0 mt-0.5">
                  <button
                    onClick={() => toggle(step.step_id)}
                    className={`text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
                      approved
                        ? "bg-green-600 text-white border-green-600 hover:bg-green-700"
                        : "bg-white text-gray-500 border-gray-300 hover:border-green-400 hover:text-green-600"
                    }`}
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => toggle(step.step_id)}
                    className={`text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
                      !approved
                        ? "bg-gray-600 text-white border-gray-600 hover:bg-gray-700"
                        : "bg-white text-gray-500 border-gray-300 hover:border-gray-400"
                    }`}
                  >
                    Reject
                  </button>
                </div>
              )}
              {done && (
                <span className={`text-xs font-medium px-2 py-1 rounded shrink-0 ${approved ? "text-green-700 bg-green-50" : "text-gray-400 bg-gray-100"}`}>
                  {approved ? "Applied" : "Skipped"}
                </span>
              )}
            </li>
          );
        })}
      </ul>

      {!done && (
        <div className="px-5 py-3 border-t border-gray-100 flex items-center gap-3">
          <button
            onClick={apply}
            disabled={executing || approvedCount === 0}
            className="bg-blue-600 text-white text-sm font-medium px-5 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {executing ? "Applying…" : `Apply ${approvedCount} fix${approvedCount !== 1 ? "es" : ""}`}
          </button>
          {statusMsg && <span className="text-xs text-gray-500">{statusMsg}</span>}
          {approvedCount === 0 && (
            <span className="text-xs text-gray-400">Approve at least one fix to continue.</span>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// FeatureApprovalCard
// ---------------------------------------------------------------------------

function FeatureApprovalCard({
  plan,
  datasetId,
  versionId,
  workspaceId,
  userId,
  onResult,
}: {
  plan: FeaturePlan;
  datasetId: string;
  versionId: string;
  workspaceId: string;
  userId: string;
  onResult: (text: string) => void;
}) {
  const features = plan.plan_json.features;
  const initialDecisions = Object.fromEntries(
    features.map((f) => [f.feature_id, "approve" as "approve" | "reject"])
  );
  const [decisions, setDecisions] = useState<Record<string, "approve" | "reject">>(initialDecisions);
  const [executing, setExecuting] = useState(false);
  const [done, setDone] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  function toggle(featureId: string) {
    if (done) return;
    setDecisions((prev) => ({
      ...prev,
      [featureId]: prev[featureId] === "approve" ? "reject" : "approve",
    }));
  }

  const approvedCount = Object.values(decisions).filter((d) => d === "approve").length;

  async function apply() {
    if (approvedCount === 0) return;
    setExecuting(true);
    setStatusMsg("Submitting…");
    try {
      const decisionItems = features.map((f) => ({
        feature_id: f.feature_id,
        decision: decisions[f.feature_id],
      }));
      const job = await executeFeaturePlan(plan.feature_plan_id, {
        workspace_id: workspaceId,
        dataset_id: datasetId,
        input_dataset_version_id: versionId,
        executed_by_user_id: userId,
        decisions: decisionItems,
      });
      setStatusMsg("Adding features…");
      await pollJob(
        job.job_id,
        () => {
          setDone(true);
          setStatusMsg(null);
          onResult(`Features added. A new copy with calculated metrics was created. Switch to the Versions tab to see it, then select it from the version picker to analyse it.`);
        },
        (msg) => {
          setStatusMsg(null);
          setExecuting(false);
          onResult(`Feature execution failed: ${msg}`);
        }
      );
    } catch (e) {
      setStatusMsg(null);
      setExecuting(false);
      onResult(`Error adding features: ${String(e)}`);
    }
  }

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-100">
        <p className="text-sm font-semibold text-gray-800">
          Suggested features — {features.length} available
        </p>
        <p className="text-xs text-gray-400 mt-0.5">
          Approve the features you want to add. A new copy will be created with the new columns.
        </p>
      </div>

      <ul className="divide-y divide-gray-50">
        {features.map((feat) => {
          const approved = decisions[feat.feature_id] === "approve";
          return (
            <li
              key={feat.feature_id}
              className={`px-5 py-4 flex items-start gap-4 transition-colors ${approved ? "bg-white" : "bg-gray-50 opacity-60"}`}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="text-xs font-semibold text-gray-800">
                    {feat.display_name || feat.feature_name}
                  </span>
                  <span className="text-[10px] font-medium text-purple-700 bg-purple-50 px-1.5 py-0.5 rounded capitalize">
                    {feat.operation_type.replace(/_/g, " ")}
                  </span>
                </div>
                {feat.description && (
                  <p className="text-xs text-gray-600">{feat.description}</p>
                )}
                {feat.formula_display && (
                  <p className="text-xs font-mono text-gray-400 mt-0.5 bg-gray-50 px-2 py-0.5 rounded inline-block">
                    {feat.formula_display}
                  </p>
                )}
              </div>

              {!done && (
                <div className="flex gap-1.5 shrink-0 mt-0.5">
                  <button
                    onClick={() => toggle(feat.feature_id)}
                    className={`text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
                      approved
                        ? "bg-green-600 text-white border-green-600 hover:bg-green-700"
                        : "bg-white text-gray-500 border-gray-300 hover:border-green-400 hover:text-green-600"
                    }`}
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => toggle(feat.feature_id)}
                    className={`text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
                      !approved
                        ? "bg-gray-600 text-white border-gray-600 hover:bg-gray-700"
                        : "bg-white text-gray-500 border-gray-300 hover:border-gray-400"
                    }`}
                  >
                    Reject
                  </button>
                </div>
              )}
              {done && (
                <span className={`text-xs font-medium px-2 py-1 rounded shrink-0 ${approved ? "text-green-700 bg-green-50" : "text-gray-400 bg-gray-100"}`}>
                  {approved ? "Added" : "Skipped"}
                </span>
              )}
            </li>
          );
        })}
      </ul>

      {!done && (
        <div className="px-5 py-3 border-t border-gray-100 flex items-center gap-3">
          <button
            onClick={apply}
            disabled={executing || approvedCount === 0}
            className="bg-purple-600 text-white text-sm font-medium px-5 py-2 rounded-lg hover:bg-purple-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {executing ? "Adding…" : `Add ${approvedCount} feature${approvedCount !== 1 ? "s" : ""}`}
          </button>
          {statusMsg && <span className="text-xs text-gray-500">{statusMsg}</span>}
          {approvedCount === 0 && (
            <span className="text-xs text-gray-400">Approve at least one feature to continue.</span>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// OutputCard and table/visual sub-cards (used inside MessageBubble)
// ---------------------------------------------------------------------------

function OutputCard({
  output,
  datasetId,
  versionId,
}: {
  output: AnalyticsOutput;
  datasetId: string;
  versionId: string;
}) {
  if (output.output_type === "text") {
    return (
      <div className="bg-white border border-gray-200 rounded-xl px-5 py-4 space-y-2">
        <p className="text-sm font-semibold text-gray-800">{output.title}</p>
        <p className="text-sm text-gray-700 whitespace-pre-wrap">{output.content}</p>
        {output.references.length > 0 && (
          <ul className="text-xs text-gray-400 list-disc list-inside">
            {output.references.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        )}
      </div>
    );
  }

  if (output.output_type === "table") {
    return <TableOutputCard output={output} datasetId={datasetId} versionId={versionId} />;
  }

  if (output.output_type === "visual") {
    return <VisualOutputCard output={output} datasetId={datasetId} versionId={versionId} />;
  }

  if (output.output_type === "mixed") {
    return (
      <div className="space-y-3">
        <p className="text-sm text-gray-500">{output.summary}</p>
        {output.outputs.map((o, i) => (
          <OutputCard key={i} output={o} datasetId={datasetId} versionId={versionId} />
        ))}
      </div>
    );
  }

  return null;
}

function TableOutputCard({
  output,
  datasetId,
  versionId,
}: {
  output: TableOutput;
  datasetId: string;
  versionId: string;
}) {
  const [saveName, setSaveName] = useState(output.title);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [showSave, setShowSave] = useState(false);

  async function doSave() {
    setSaving(true);
    setSaveMsg(null);
    try {
      await saveTableAsView({
        dataset_id: datasetId,
        dataset_version_id: versionId,
        name: saveName || output.title,
        columns: output.columns,
        rows: output.preview_rows,
      });
      setSaveMsg("Saved as view.");
      setShowSave(false);
    } catch (e) {
      setSaveMsg(`Failed: ${String(e)}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-gray-800">{output.title}</p>
          {output.description && (
            <p className="text-xs text-gray-400 mt-0.5">{output.description}</p>
          )}
        </div>
        <span className="text-xs text-gray-400">{output.row_count.toLocaleString()} rows</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50 text-gray-500">
              {output.columns.map((c) => (
                <th key={c} className="text-left px-4 py-2 font-medium">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {output.preview_rows.map((row, i) => (
              <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                {(row as unknown[]).map((cell, j) => (
                  <td key={j} className="px-4 py-2 text-gray-700">
                    {cell == null ? <span className="text-gray-300">—</span> : String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="px-5 py-3 border-t border-gray-100 flex items-center gap-3 flex-wrap">
        {!showSave && (
          <button onClick={() => setShowSave(true)} className="text-xs text-blue-600 hover:underline">
            Save as view
          </button>
        )}
        {showSave && (
          <>
            <input
              className="border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 w-48"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="View name"
            />
            <button
              onClick={doSave}
              disabled={saving}
              className="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700 disabled:opacity-40"
            >
              {saving ? "Saving…" : "Save"}
            </button>
            <button onClick={() => setShowSave(false)} className="text-xs text-gray-400 hover:text-gray-600">
              Cancel
            </button>
          </>
        )}
        {saveMsg && <span className="text-xs text-gray-500">{saveMsg}</span>}
      </div>
    </div>
  );
}

function VisualOutputCard({
  output,
  datasetId,
  versionId,
}: {
  output: VisualOutput;
  datasetId: string;
  versionId: string;
}) {
  const [saveTitle, setSaveTitle] = useState(output.title);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [showSave, setShowSave] = useState(false);

  const chartData = (output.chart_spec_json?.data ?? []) as Record<string, unknown>[];
  const dataColumns = chartData.length > 0 ? Object.keys(chartData[0]) : [];

  async function doSave() {
    setSaving(true);
    setSaveMsg(null);
    try {
      await saveVisualToVisuals({
        dataset_id: datasetId,
        dataset_version_id: versionId,
        title: saveTitle || output.title,
        chart_type: output.chart_type,
        chart_spec_json: output.chart_spec_json,
      });
      setSaveMsg("Saved to visuals.");
      setShowSave(false);
    } catch (e) {
      setSaveMsg(`Failed: ${String(e)}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-gray-800">{output.title}</p>
          {output.description && (
            <p className="text-xs text-gray-400 mt-0.5">{output.description}</p>
          )}
        </div>
        <span className="text-xs font-medium text-purple-600 bg-purple-50 px-2 py-0.5 rounded capitalize">
          {output.chart_type} chart
        </span>
      </div>

      {chartData.length > 0 && dataColumns.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50 text-gray-500">
                {dataColumns.map((c) => (
                  <th key={c} className="text-left px-4 py-2 font-medium">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {chartData.slice(0, 20).map((row, i) => (
                <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                  {dataColumns.map((c) => (
                    <td key={c} className="px-4 py-2 text-gray-700">
                      {row[c] == null ? <span className="text-gray-300">—</span> : String(row[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {chartData.length > 20 && (
            <p className="text-xs text-gray-400 px-4 py-2">
              Showing 20 of {chartData.length} data points.
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs text-gray-400 px-5 py-3">No chart data to preview.</p>
      )}

      <div className="px-5 py-3 border-t border-gray-100 flex items-center gap-3 flex-wrap">
        {!showSave && (
          <button onClick={() => setShowSave(true)} className="text-xs text-purple-600 hover:underline">
            Save visual
          </button>
        )}
        {showSave && (
          <>
            <input
              className="border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-purple-500 w-48"
              value={saveTitle}
              onChange={(e) => setSaveTitle(e.target.value)}
              placeholder="Visual title"
            />
            <button
              onClick={doSave}
              disabled={saving}
              className="text-xs bg-purple-600 text-white px-3 py-1 rounded hover:bg-purple-700 disabled:opacity-40"
            >
              {saving ? "Saving…" : "Save"}
            </button>
            <button onClick={() => setShowSave(false)} className="text-xs text-gray-400 hover:text-gray-600">
              Cancel
            </button>
          </>
        )}
        {saveMsg && <span className="text-xs text-gray-500">{saveMsg}</span>}
      </div>
    </div>
  );
}
