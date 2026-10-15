import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";

if (!process.env.CONTROL_PLANE_TEST_DATABASE_URL) {
  console.error(
    "CONTROL_PLANE_TEST_DATABASE_URL is required; refusing to skip real PostgreSQL checks",
  );
  process.exitCode = 1;
} else {
  const require = createRequire(import.meta.url);
  const result = spawnSync(
    process.execPath,
    [
      path.join(path.dirname(require.resolve("vitest/package.json")), "vitest.mjs"),
      "run",
      "src/persistence.postgres.spec.ts",
    ],
    { stdio: "inherit", env: process.env },
  );
  process.exitCode = result.status ?? 1;
}
