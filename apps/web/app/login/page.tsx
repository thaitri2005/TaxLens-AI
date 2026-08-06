"use client";

import { FormEvent, useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const result = await signIn("credentials", { username, password, redirect: false });
    if (result?.ok) router.push("/");
    else setError("The username or password is not valid.");
    setBusy(false);
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <p className="eyebrow">TaxLens</p>
        <h1>Sign in</h1>
        <p>Sign in to search Vietnamese tax regulations and review cited answers.</p>
        <form onSubmit={submit} className="auth-form">
          <label>Username<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label>
          <label>Password<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" required /></label>
          {error && <p className="auth-error">{error}</p>}
          <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
      </section>
    </main>
  );
}
