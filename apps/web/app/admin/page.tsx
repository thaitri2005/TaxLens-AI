"use client";

import { FormEvent, useEffect, useState } from "react";
import { signOut, useSession } from "next-auth/react";

type AdminUser = { id: string; username: string; role: string; is_active: boolean; created_at: string };

export default function AdminPage() {
  const { data: session, status } = useSession();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function loadUsers() {
    const response = await fetch("/api/admin/users", { cache: "no-store" });
    if (!response.ok) { setError("Unable to load users."); return; }
    setUsers(await response.json());
  }

  useEffect(() => { if (session?.user.role === "admin") void loadUsers(); }, [session]);

  async function createUser(event: FormEvent) {
    event.preventDefault(); setError("");
    const response = await fetch("/api/admin/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password, role: "user" }) });
    if (!response.ok) { setError("User could not be created. Use a password with at least 12 characters."); return; }
    setUsername(""); setPassword(""); await loadUsers();
  }

  async function disableUser(id: string) {
    await fetch(`/api/admin/users/${id}/disable`, { method: "POST" }); await loadUsers();
  }

  async function resetPassword(id: string) {
    const nextPassword = window.prompt("Enter a new password (at least 12 characters):");
    if (!nextPassword) return;
    await fetch(`/api/admin/users/${id}/reset-password`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: nextPassword }) });
  }

  async function deleteUser(id: string) {
    if (!window.confirm("Delete this account?")) return;
    await fetch(`/api/admin/users/${id}`, { method: "DELETE" }); await loadUsers();
  }

  if (status === "loading") return <main className="auth-shell"><p>Loading…</p></main>;
  if (!session || session.user.role !== "admin") return <main className="auth-shell"><section className="auth-card"><h1>Access denied</h1><p>Administrator access is required.</p></section></main>;

  return <><header className="topbar"><a className="brand" href="/"><span className="brand-mark">TL</span><span><strong>TaxLens</strong><small>Regulatory intelligence</small></span></a><div className="topbar-actions"><a className="topbar-link" href="/">← Back to workspace</a><button className="sign-out-button" type="button" onClick={() => signOut({ callbackUrl: "/login" })}>Sign out</button></div></header><main className="shell"><section className="view admin-view"><p className="eyebrow">Administration</p><h1>User accounts</h1><p className="admin-intro">Manage access to the TaxLens workspace.</p><form onSubmit={createUser} className="auth-form admin-create-form"><label>Username<input value={username} onChange={(event) => setUsername(event.target.value)} required /></label><label>Temporary password<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" minLength={12} required /></label><button type="submit">Create user</button>{error && <p className="auth-error">{error}</p>}</form><div className="result-list">{users.map((user) => <article className="result-card user-card" key={user.id}><div className="user-card-info"><strong>{user.username}</strong><span>{user.role} · {user.is_active ? "Active" : "Disabled"}</span></div>{user.id !== session.user.id && <div className="user-actions"><button className="button-secondary" type="button" onClick={() => resetPassword(user.id)}>Reset password</button>{user.is_active && <button className="button-warning" type="button" onClick={() => disableUser(user.id)}>Disable</button>}<button className="button-danger" type="button" onClick={() => deleteUser(user.id)}>Delete</button></div>}</article>)}</div></section></main></>;
}
