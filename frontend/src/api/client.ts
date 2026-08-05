// Same-origin in both dev (Vite proxy) and prod (Flask serves the build),
// so no base URL / CORS config is needed. See vite.config.ts for the proxy.

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const message = (body && typeof body === "object" && "error" in body && String((body as { error: unknown }).error)) || res.statusText;
    throw new ApiError(message, res.status, body);
  }
  return body as T;
}
