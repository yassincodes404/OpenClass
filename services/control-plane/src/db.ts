import { Pool } from "pg";

/** Injection token so tests can substitute the control-plane database pool. */
export const CONTROL_DB = "CONTROL_DB_POOL";

export function createControlPool(): Pool {
  return new Pool({
    connectionString:
      process.env.CONTROL_PLANE_DATABASE_URL ??
      "postgresql://openclass:openclass@127.0.0.1:5432/openclass",
  });
}
