/**
 * Thin localStorage layer for placeholder auth session state only.
 *
 * Persisted to localStorage:
 *   current_user  — { user_id, username } — the logged-in session
 *
 * Everything else (workspace creation, workspace listing, membership)
 * goes through the backend API (lib/api.ts).
 */

export interface User {
  user_id: string;
  username: string;
}

function read<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(key, JSON.stringify(value));
}

// ── Session ──────────────────────────────────────────────────────────────────

export function getCurrentUser(): User | null {
  return read<User | null>("current_user", null);
}

export function setCurrentUser(user: User): void {
  write("current_user", user);
}

export function logoutUser(): void {
  if (typeof window !== "undefined") localStorage.removeItem("current_user");
}
