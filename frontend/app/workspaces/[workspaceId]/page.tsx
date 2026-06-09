"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getCurrentUser } from "@/lib/store";
import type { User } from "@/lib/store";
import {
  createDataset,
  listDatasets,
  apiGetWorkspace,
  apiAddWorkspaceMember,
  apiLookupUser,
} from "@/lib/api";
import type { ApiWorkspace } from "@/lib/api";
import type { Dataset } from "@/lib/types";

export default function WorkspacePage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [workspace, setWorkspace] = useState<ApiWorkspace | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [addMemberInput, setAddMemberInput] = useState("");
  const [addMemberError, setAddMemberError] = useState<string | null>(null);
  const [addMemberSuccess, setAddMemberSuccess] = useState<string | null>(null);
  const [addingMember, setAddingMember] = useState(false);

  useEffect(() => {
    setMounted(true);
    const u = getCurrentUser();
    if (!u) { router.replace("/"); return; }
    setUser(u);

    Promise.all([
      apiGetWorkspace(workspaceId),
      listDatasets(workspaceId),
    ])
      .then(([ws, ds]) => {
        setWorkspace(ws);
        setDatasets(ds);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [workspaceId, router]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      const ds = await createDataset(workspaceId, newName.trim());
      router.push(`/workspaces/${workspaceId}/datasets/${ds.dataset_id}`);
    } catch (e) {
      setCreateError(String(e));
      setCreating(false);
    }
  }

  async function handleAddMember(e: React.FormEvent) {
    e.preventDefault();
    const name = addMemberInput.trim().toLowerCase();
    if (!name) return;
    setAddMemberError(null);
    setAddMemberSuccess(null);
    setAddingMember(true);
    try {
      await apiLookupUser(name);
      await apiAddWorkspaceMember(workspaceId, name);
      setAddMemberInput("");
      setAddMemberSuccess(`@${name} added.`);
    } catch (e) {
      setAddMemberError(e instanceof Error ? e.message : `User "${name}" not found.`);
    } finally {
      setAddingMember(false);
    }
  }

  if (!mounted) return null;

  return (
    <main className="min-h-screen bg-gray-50">
      <nav className="border-b border-gray-200 bg-white px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3 text-sm text-gray-500">
          <button onClick={() => router.push("/workspaces")} className="hover:text-gray-800">
            Workspaces
          </button>
          <span>/</span>
          <span className="text-gray-800 font-medium">
            {workspace?.name ?? workspaceId.slice(0, 8)}
          </span>
        </div>

        <form onSubmit={handleAddMember} className="flex items-center gap-2">
          <input
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500 w-36"
            placeholder="Add user by username"
            value={addMemberInput}
            onChange={(e) => {
              setAddMemberInput(e.target.value);
              setAddMemberError(null);
              setAddMemberSuccess(null);
            }}
          />
          <button
            type="submit"
            disabled={!addMemberInput.trim() || addingMember}
            className="text-xs bg-gray-100 text-gray-700 px-3 py-1.5 rounded-lg hover:bg-gray-200 disabled:opacity-40"
          >
            Add
          </button>
          {addMemberError && <span className="text-xs text-red-500">{addMemberError}</span>}
          {addMemberSuccess && <span className="text-xs text-green-600">{addMemberSuccess}</span>}
        </form>
      </nav>

      <div className="max-w-5xl mx-auto px-6 py-10">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">
            {workspace?.name ?? "Workspace"}
          </h1>
          {user && <p className="text-xs text-gray-400">@{user.username}</p>}
        </div>

        {error && <p className="text-sm text-red-500 mb-4">{error}</p>}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Create new dataset card */}
          {!showCreate ? (
            <button
              onClick={() => setShowCreate(true)}
              className="flex flex-col items-center justify-center bg-white border-2 border-dashed border-gray-300 rounded-xl p-8 hover:border-blue-400 hover:bg-blue-50 transition text-gray-400 hover:text-blue-600 min-h-36"
            >
              <span className="text-3xl mb-2">+</span>
              <span className="text-sm font-medium">New dataset</span>
            </button>
          ) : (
            <div className="bg-white border-2 border-blue-400 rounded-xl p-5 space-y-3 min-h-36">
              <p className="text-sm font-medium text-gray-700">Dataset name</p>
              <form onSubmit={handleCreate} className="space-y-2">
                <input
                  autoFocus
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="e.g. Sales Q1 2024"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  disabled={creating}
                />
                {createError && <p className="text-xs text-red-500">{createError}</p>}
                <div className="flex gap-2">
                  <button
                    type="submit"
                    disabled={creating || !newName.trim()}
                    className="bg-blue-600 text-white text-xs font-medium px-3 py-1.5 rounded-lg hover:bg-blue-700 disabled:opacity-40"
                  >
                    {creating ? "Creating…" : "Create"}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setShowCreate(false); setNewName(""); setCreateError(null); }}
                    className="text-xs text-gray-500 px-3 py-1.5 rounded-lg hover:bg-gray-100"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          )}

          {loading && (
            <div className="bg-white border border-gray-200 rounded-xl p-6 text-sm text-gray-400 flex items-center justify-center min-h-36">
              Loading…
            </div>
          )}

          {!loading && datasets.map((ds) => (
            <button
              key={ds.dataset_id}
              onClick={() => router.push(`/workspaces/${workspaceId}/datasets/${ds.dataset_id}`)}
              className="text-left bg-white border border-gray-200 rounded-xl p-5 hover:border-blue-400 hover:shadow-sm transition group min-h-36 flex flex-col justify-between"
            >
              <div>
                <p className="text-sm font-semibold text-gray-900 group-hover:text-blue-600 mb-1">
                  {ds.name}
                </p>
              </div>
              <p className="text-xs text-gray-400 mt-3">
                Created {new Date(ds.created_at).toLocaleDateString()}
              </p>
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}
