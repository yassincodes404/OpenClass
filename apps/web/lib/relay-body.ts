const MAX_BYTES = 5 * 1024 * 1024;
const TIMEOUT_MS = 10_000;

export class RelayBodyError extends Error {
  constructor(
    public readonly status: 400 | 408 | 413,
    message: string,
  ) {
    super(message);
  }
}

/** Bound consumption, not just forwarding; Content-Length is only a hint. */
export async function readRelayBody(
  request: Request,
  { maxBytes = MAX_BYTES, timeoutMs = TIMEOUT_MS } = {},
): Promise<string | undefined> {
  if (!request.body || ["GET", "HEAD"].includes(request.method)) return undefined;
  const declared = request.headers.get("content-length");
  if (declared && /^\d+$/.test(declared) && Number(declared) > maxBytes) {
    void request.body.cancel().catch(() => undefined);
    throw new RelayBodyError(413, "Request too large");
  }
  const reader = request.body.getReader();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new RelayBodyError(408, "Request body timed out")), timeoutMs);
  });
  const decoder = new TextDecoder();
  const parts: string[] = [];
  let consumed = 0;
  try {
    for (;;) {
      const { done, value } = await Promise.race([reader.read(), deadline]);
      if (done) break;
      consumed += value.byteLength;
      if (consumed > maxBytes) throw new RelayBodyError(413, "Request too large");
      parts.push(decoder.decode(value, { stream: true }));
    }
    parts.push(decoder.decode());
    return parts.join("");
  } catch (error) {
    // Do not await a hostile or disconnected producer's cancellation promise.
    void reader.cancel().catch(() => undefined);
    if (error instanceof RelayBodyError) throw error;
    throw new RelayBodyError(400, "Request body unavailable");
  } finally {
    if (timer !== undefined) clearTimeout(timer);
    reader.releaseLock();
  }
}
