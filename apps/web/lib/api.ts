// A scaled-to-zero API answers 502-504 while it starts; reads are retried instead of failing.
export const RETRY_DELAYS_MS = [3000, 8000];

export const SLOW_REQUEST_MS = 4000;

export const UNAVAILABLE_STATUSES = new Set([502, 503, 504]);

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  // Reads are retried while the API starts; a question (POST) is never sent twice.
  const retries = !options?.method || options.method === "GET" ? RETRY_DELAYS_MS.length : 0;
  for (let attempt = 0; ; attempt += 1) {
    let response: Response | null = null;
    try {
      response = await fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...options });
    } catch {
      response = null;
    }
    if ((response === null || UNAVAILABLE_STATUSES.has(response.status)) && attempt < retries) {
      await new Promise(resolve => setTimeout(resolve, RETRY_DELAYS_MS[attempt]));
      continue;
    }
    if (response === null) throw new Error("The service could not be reached.");
    const body = await response.json().catch(() => ({}));
    // The sign-in session (8 hours) has ended: go back to the login page.
    if (response.status === 401 && body.detail === "Authentication required") window.location.assign("/login");
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "The request could not be completed.");
    return body as T;
  }
}
