import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import pg from "pg";

export const migrationsDirectory = fileURLToPath(new URL("../migrations/", import.meta.url));

/** One locked transaction: failed SQL/checksum validation never stamps a version. */
export async function migrate(pool, directory = migrationsDirectory) {
  const files = (await readdir(directory))
    .filter((name) => /^\d{4}_[a-z0-9_]+\.sql$/.test(name))
    .sort();
  if (!files.length) throw new Error("No control-plane migrations found");
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await client.query(
      "SELECT pg_advisory_xact_lock(hashtextextended(current_database() || ':' || current_schema() || ':control-migrations', 0))",
    );
    await client.query(`CREATE TABLE IF NOT EXISTS control_schema_migrations (
      version text PRIMARY KEY, checksum varchar(64) NOT NULL,
      applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
    )`);
    const history = await client.query(
      "SELECT version, checksum FROM control_schema_migrations ORDER BY version",
    );
    const known = new Map(history.rows.map((row) => [row.version, row.checksum]));
    for (const version of known.keys()) {
      if (!files.includes(version))
        throw new Error("Applied migration is missing from the reviewed migration set");
    }
    const applied = [];
    for (const version of files) {
      const sql = await readFile(path.join(directory, version), "utf8");
      const checksum = createHash("sha256").update(sql).digest("hex");
      if (known.has(version)) {
        if (known.get(version) !== checksum)
          throw new Error(`Migration checksum mismatch: ${version}`);
        continue;
      }
      if (history.rows.some((row) => row.version > version)) {
        throw new Error("Out-of-order migration requires explicit operator review");
      }
      await client.query(sql);
      await client.query(
        "INSERT INTO control_schema_migrations (version, checksum) VALUES ($1, $2)",
        [version, checksum],
      );
      applied.push(version);
    }
    await client.query("COMMIT");
    return applied;
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const url = process.env.CONTROL_PLANE_DATABASE_URL;
  if (!url) {
    console.error("CONTROL_PLANE_DATABASE_URL is required for explicit migrations");
    process.exitCode = 1;
  } else {
    const pool = new pg.Pool({ connectionString: url, connectionTimeoutMillis: 5_000 });
    try {
      const applied = await migrate(pool);
      console.log(
        JSON.stringify({
          event: "control.migrations_applied",
          count: applied.length,
          versions: applied,
        }),
      );
    } catch {
      // Database errors can contain connection credentials or user-controlled rows.
      console.error(
        JSON.stringify({ event: "control.migrations_failed", code: "migration_failed" }),
      );
      process.exitCode = 1;
    } finally {
      await pool.end();
    }
  }
}
