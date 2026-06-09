"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getCurrentUser, setCurrentUser } from "@/lib/store";
import { apiLogin } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const user = getCurrentUser();
    if (user) router.replace("/workspaces");
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const name = username.trim().toLowerCase();
    if (!name) return;
    if (!/^[a-z0-9_-]+$/.test(name)) {
      setError("Username must be alphanumeric (letters, numbers, _ or -).");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const user = await apiLogin(name);
      setCurrentUser({ user_id: user.user_id, username: user.username });
      router.push("/workspaces");
    } catch {
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  if (!mounted) return null;

  return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center px-6">
      <div className="max-w-sm w-full">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">AI Data Analyst</h1>
          <p className="text-sm text-gray-500 mt-2">
            Enter a username to sign in or create a new account.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
            <input
              autoFocus
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="e.g. alice"
              value={username}
              onChange={(e) => { setUsername(e.target.value); setError(null); }}
            />
            {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
          </div>
          <button
            type="submit"
            disabled={!username.trim() || loading}
            className="w-full bg-blue-600 text-white text-sm font-medium py-2 rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Signing in…" : "Continue"}
          </button>
          <p className="text-xs text-center text-gray-400">
            New username → account created automatically.
          </p>
        </form>
      </div>
    </main>
  );
}
