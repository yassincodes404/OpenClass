export type ApiError = { status: number; message: string };

export class ControlApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

/** Fetch a control-plane endpoint with the session bearer token. */
export async function controlFetch(path: string, token: string | undefined, init?: RequestInit): Promise<unknown> {
  const response = await fetch(`/control${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { "content-type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (response.status === 401) throw new ControlApiError(401, "Session expired");
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { message?: string };
    throw new ControlApiError(response.status, payload.message ?? `Request failed (${response.status})`);
  }
  return response.json();
}
