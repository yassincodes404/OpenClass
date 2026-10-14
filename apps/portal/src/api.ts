import { ControlApiError, type ControlRequestInit, OpenClassControlClient } from "@openclass/sdk";

export { ControlApiError, type ControlRequestInit, OpenClassControlClient };

export type ApiError = { status: number; message: string };

export const controlClient = new OpenClassControlClient({ baseUrl: "/control" });

/** Fetch a control-plane endpoint with the session bearer token via @openclass/sdk. */
export async function controlFetch<T = unknown>(
  path: string,
  tokenOrInit?: string | ControlRequestInit,
  maybeInit?: ControlRequestInit,
): Promise<T> {
  const init: ControlRequestInit | undefined =
    typeof tokenOrInit === "string" || tokenOrInit === undefined
      ? maybeInit || tokenOrInit !== undefined
        ? { ...maybeInit, ...(tokenOrInit ? { token: tokenOrInit } : {}) }
        : undefined
      : tokenOrInit;
  return controlClient.request<T>(path, init);
}
