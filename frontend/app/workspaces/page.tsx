"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getCurrentUser, logoutUser } from "@/lib/store";
import type { User } from "@/lib/store";
import {
  apiCreateWorkspace,
  apiListUserWorkspaces,
  apiLookupUser,
  apiAddWorkspaceMember,
} from "@/lib/api";
import type { ApiWorkspace } from "@/lib/api";

export default function WorkspacesPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [workspaces, setWorkspaces] = useState<ApiWorkspace[]>([]);
  const [mounted, setMounted] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [addMembers, setAddMembers] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    setMounted(true);
    const u = getCurrentUser();
    if (!u) { router.replace("/"); return; }
    setUser(u);
    apiListUserWorkspaces(u.user_id)
      .then(setWorkspaces)
      .catch(() => setLoadError("Could not load workspaces."));
  }, [router]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!user || !newName.trim()) return;
    setCreateError(null);
    setCreating(true);

    const extraNames = addMembers
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);

    try {
      // Validate extra members exist before creating
      for (const name of extraNames) {
        await apiLookupUser(name).catch(() => {
          throw new Error(`User "${name}" not found.`);
        });
      }

      const ws = await apiCreateWorkspace(newName.trim(), user.user_id);

      for (const name of extraNames) {
        await apiAddWorkspaceMember(ws.workspace_id, name).catch(() => {/* ignore individual failures */});
      }

      setNewName("");
      setAddMembers("");
      setShowCreate(false);
      const updated = await apiListUserWorkspaces(user.user_id);
      setWorkspaces(updated);
      router.push(`/workspaces/${ws.workspace_id}`);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create workspace.");
    } finally {
      setCreating(false);
    }
  }

  function handleLogout() {
    logoutUser();
    router.push("/");
  }

  if (!mounted || !user) return null;

  return (
    <main className="min-h-screen bg-gray-50">
      <nav className="border-b border-gray-200 bg-white px-6 py-3 flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-800">AI Data Analyst</span>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-gray-500">@{user.username}</span>
          <button onClick={handleLogout} className="text-gray-400 hover:text-gray-700">
            Sign out
          </button>
        </div>
      </nav>

      <div className="max-w-3xl mx-auto px-6 py-10 space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-900">Workspaces</h1>
          <button
            onClick={() => setShowCreate((v) => !v)}
            className="bg-blue-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
          >
            + New workspace
          </button>
        </div>

        {loadError && <p className="text-sm text-red-500">{loadError}</p>}

        {showCreate && (
          <form
            onSubmit={handleCreate}
            className="bg-white border border-gray-200 rounded-xl p-5 space-y-3"
          >
            <p className="text-sm font-medium text-gray-700">Create workspace</p>
            <input
              autoFocus
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Workspace name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <input
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Add members by username, comma-separated (optional)"
              value={addMembers}
              onChange={(e) => { setAddMembers(e.target.value); setCreateError(null); }}
            />
            {createError && <p className="text-xs text-red-500">{createError}</p>}
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={!newName.trim() || creating}
                className="bg-blue-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {creating ? "Creating…" : "Create"}
              </button>
              <button
                type="button"
                onClick={() => { setShowCreate(false); setCreateError(null); }}
                className="text-sm text-gray-500 px-4 py-2 rounded-lg hover:bg-gray-100"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {workspaces.length === 0 && !showCreate && !loadError && (
          <p className="text-sm text-gray-400">No workspaces yet. Create one to get started.</p>
        )}

        <ul className="space-y-3">
          {workspaces.map((ws) => (
            <li key={ws.workspace_id}>
              <button
                onClick={() => router.push(`/workspaces/${ws.workspace_id}`)}
                className="w-full text-left bg-white border border-gray-200 rounded-xl px-5 py-4 hover:border-blue-400 hover:shadow-sm transition group"
              >
                <p className="text-sm font-semibold text-gray-900 group-hover:text-blue-600">
                  {ws.name}
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  Created {new Date(ws.created_at).toLocaleDateString()}
                </p>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
