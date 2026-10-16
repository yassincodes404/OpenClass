import { ControlApiError, OpenClassControlClient } from "@openclass/sdk";
import { readRelayBody, RelayBodyError } from "../../../lib/relay-body";

// The browser supplies ONLY its end-user bearer token. No engine credentials.
const control = new OpenClassControlClient({
  baseUrl: `${(process.env.CONTROL_PLANE_URL ?? process.env.CONTROL_PLANE_BASE_URL ?? "http://127.0.0.1:7400").replace(/\/$/, "")}/control`,
});
async function relay(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ") || authorization.length > 32_768)
    return Response.json({ message: "Authentication required" }, { status: 401 });
  const { path } = await context.params;
  if (path.some((segment) => !/^[a-zA-Z0-9_-]+$/.test(segment)))
    return Response.json({ message: "Invalid control path" }, { status: 400 });
  const headers: Record<string, string> = {};
  const correlation = request.headers.get("x-correlation-id");
  if (correlation && /^[a-zA-Z0-9._:-]{1,128}$/.test(correlation))
    headers["X-Correlation-ID"] = correlation;
  const key = request.headers.get("idempotency-key");
  if (key && /^[a-zA-Z0-9._:-]{1,200}$/.test(key)) headers["Idempotency-Key"] = key;
  try {
    const body = await readRelayBody(request);
    const value = await control.requestWithStatus(
      `/${path.join("/")}${new URL(request.url).search}`,
      {
        method: request.method,
        token: authorization.slice(7),
        headers,
        body: body || undefined,
        cache: "no-store",
        signal: AbortSignal.timeout(60_000),
      },
    );
    const responseHeaders = { "Cache-Control": "no-store" };
    return value.status === 204
      ? new Response(null, { status: value.status, headers: responseHeaders })
      : Response.json(value.body, { status: value.status, headers: responseHeaders });
  } catch (error) {
    const known = error instanceof ControlApiError || error instanceof RelayBodyError;
    const status = known ? error.status : 502;
    return Response.json(
      { message: known ? error.message : "Control plane unavailable" },
      { status, headers: { "Cache-Control": "no-store" } },
    );
  }
}
export { relay as GET, relay as POST, relay as PATCH, relay as DELETE };
