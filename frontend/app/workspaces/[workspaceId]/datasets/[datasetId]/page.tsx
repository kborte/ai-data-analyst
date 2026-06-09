"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  analyticsAsk,
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
  Dataset,
  DatasetFile,
  DatasetVersion,
  DatasetTable,
  DataProfile,
  SavedView,
  SavedVisual,
  TableOutput,
  VisualOutput,
} from "@/lib/types";

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
              <ChatPanel datasetId={datasetId} versionId={selectedVersionId} />
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
// Chat / Analytics Ask (FE1G-H)
// ---------------------------------------------------------------------------

function ChatPanel({
  datasetId,
  versionId,
}: {
  datasetId: string;
  versionId: string;
}) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [output, setOutput] = useState<AnalyticsOutput | null>(null);

  async function ask() {
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setOutput(null);
    try {
      const res = await analyticsAsk(datasetId, versionId, question.trim());
      setOutput(res.output);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <input
          className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Ask a question about your dataset…"
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
          {loading ? "Thinking…" : "Ask"}
        </button>
      </div>

      {error && (
        <p className="text-sm text-red-500 bg-red-50 border border-red-100 rounded-lg px-4 py-3">
          {error}
        </p>
      )}

      {output && (
        <OutputCard
          output={output}
          datasetId={datasetId}
          versionId={versionId}
        />
      )}
    </div>
  );
}

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
    return (
      <TableOutputCard
        output={output}
        datasetId={datasetId}
        versionId={versionId}
      />
    );
  }

  if (output.output_type === "visual") {
    return (
      <VisualOutputCard
        output={output}
        datasetId={datasetId}
        versionId={versionId}
      />
    );
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
        <span className="text-xs text-gray-400">
          {output.row_count.toLocaleString()} rows
        </span>
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
          <button
            onClick={() => setShowSave(true)}
            className="text-xs text-blue-600 hover:underline"
          >
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
            <button
              onClick={() => setShowSave(false)}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
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
          <button
            onClick={() => setShowSave(true)}
            className="text-xs text-purple-600 hover:underline"
          >
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
            <button
              onClick={() => setShowSave(false)}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
              Cancel
            </button>
          </>
        )}
        {saveMsg && <span className="text-xs text-gray-500">{saveMsg}</span>}
      </div>
    </div>
  );
}
