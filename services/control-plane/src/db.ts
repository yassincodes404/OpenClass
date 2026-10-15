import { Pool } from "pg";
import type { PoolClient } from "pg";
import { AsyncLocalStorage } from "node:async_hooks";

/** Injection token so tests can substitute the control-plane database pool. */
export const CONTROL_DB = "CONTROL_DB_POOL";

const transactions = new AsyncLocalStorage<{ pool: Pool; client: PoolClient }>();

/** Route every injected service's query through the same request transaction. */
export function transactionalPool(pool: Pool): Pool {
  const proxy = new Proxy(pool, {
    get(target, property) {
      if (property === "query") {
        return (...args: Parameters<Pool["query"]>) => {
          const active = transactions.getStore();
          const executor = active?.pool === proxy ? active.client : target;
          return executor.query(...args);
        };
      }
      const value = Reflect.get(target, property, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
  return proxy;
}

export async function controlTransaction<T>(
  pool: Pool,
  operation: (client: PoolClient) => Promise<T>,
): Promise<T> {
  const active = transactions.getStore();
  if (active?.pool === pool) return operation(active.client);
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const result = await transactions.run({ pool, client }, () => operation(client));
    await client.query("COMMIT");
    return result;
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
}

export function createControlPool(): Pool {
  return transactionalPool(
    new Pool({
      connectionString:
        process.env.CONTROL_PLANE_DATABASE_URL ??
        "postgresql://openclass:openclass@127.0.0.1:5432/openclass",
    }),
  );
}
