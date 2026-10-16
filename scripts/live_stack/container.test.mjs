import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";

const filename = fileURLToPath(new URL("../../docker/control-plane.cjs", import.meta.url));
const source = await readFile(filename, "utf8");
const sql = "-- reviewed migration\n";
const migration = {
  version: "0001_initial.sql",
  checksum: createHash("sha256").update(sql).digest("hex"),
};

// These are transport-bootstrap unit tests, not HTTP/controller substitutes for
// the separate real-Keycloak/PostgreSQL Playwright gate.
async function bootstrap(options = {}) {
  const observed = { errors: [], queries: [], middleware: [], dependencies: [] };
  const pool = {
    query: async (query) => {
      observed.queries.push(query);
      if (options.databaseFailure) throw new Error("credential=must-not-leak");
      return { rows: options.history ?? [migration] };
    },
  };
  const correlationMiddleware = () => {};
  const appModule = {};
  const app = {
    use: (middleware) => observed.middleware.push(middleware),
    useBodyParser: (...args) => (observed.bodyParser = args),
    get: (key) => {
      assert.equal(key, "CONTROL_DB_POOL");
      return pool;
    },
    getHttpAdapter: () => ({
      get: (route, handler) => {
        assert.equal(route, "/health/ready");
        observed.ready = handler;
      },
    }),
    enableShutdownHooks: () => {},
    listen: (...args) => (observed.listener = args),
  };
  const modules = {
    "reflect-metadata": {},
    "@nestjs/core": {
      NestFactory: {
        create: async (module, config) => {
          assert.equal(module, appModule);
          assert.equal(config.logger.options.json, true);
          return app;
        },
      },
    },
    "@nestjs/common": {
      ConsoleLogger: class {
        constructor(options) {
          this.options = options;
        }
      },
    },
    "../dist/app.module.js": { AppModule: appModule },
    "../dist/db.js": { CONTROL_DB: "CONTROL_DB_POOL" },
    "../dist/request-context.js": { correlationMiddleware },
    "node:crypto": { createHash },
    "node:fs/promises": {
      readdir: async () => options.files ?? [migration.version],
      readFile: async () => sql,
    },
    "node:path": path,
    "node:net": {
      createServer: () => ({
        once: () => {},
        listen: (port, host, ready) => {
          observed.bridge = { port, host };
          ready();
        },
      }),
    },
  };
  await vm.runInNewContext(source, {
    require: (name) => {
      assert.ok(name in modules, `Unexpected bootstrap dependency: ${name}`);
      return modules[name];
    },
    __dirname: path.dirname(filename),
    URL,
    AbortSignal,
    console: { error: (message) => observed.errors.push(message) },
    fetch: async (url) => {
      observed.dependencies.push(url);
      return { ok: !options.dependencyFailure };
    },
    process: {
      env: {
        KEYCLOAK_ISSUER_URL: options.issuer ?? "http://127.0.0.1:18081/realms/openclass-local",
        KEYCLOAK_CONTAINER_HOST: "keycloak",
        ENGINE_BASE_URL: "http://server:7331",
      },
      exit: (code) => (observed.exitCode = code),
    },
  });
  observed.correlationMiddleware = correlationMiddleware;
  return observed;
}

async function readiness(observed) {
  const result = {
    status(code) {
      this.code = code;
      return this;
    },
    json(body) {
      this.body = body;
    },
  };
  await observed.ready({}, result);
  return result;
}

test("container keeps application middleware, shared pool, bounded body and private issuer bridge", async () => {
  const result = await bootstrap();
  assert.deepEqual(result.middleware, [result.correlationMiddleware]);
  assert.equal(result.bodyParser[0], "json");
  assert.equal(result.bodyParser[1].limit, "5mb");
  assert.deepEqual(result.listener, [7400, "0.0.0.0"]);
  assert.deepEqual(result.bridge, { port: 18081, host: "127.0.0.1" });
  assert.equal(result.exitCode, undefined);
});

test("readiness verifies migration history and both real dependencies without applying SQL", async () => {
  const result = await bootstrap();
  const response = await readiness(result);
  assert.equal(response.code, 200);
  assert.deepEqual(result.queries, [
    "SELECT version, checksum FROM control_schema_migrations ORDER BY version",
  ]);
  assert.deepEqual(result.dependencies, [
    "http://server:7331/health/ready",
    "http://127.0.0.1:18081/realms/openclass-local/protocol/openid-connect/certs",
  ]);
});

for (const history of [
  [],
  [{ ...migration, checksum: "tampered" }],
  [{ ...migration, version: "0000_unreviewed.sql" }],
  [migration, { ...migration, version: "9999_unknown.sql" }],
]) {
  test(`readiness rejects missing or changed migration history: ${JSON.stringify(history)}`, async () => {
    assert.equal((await readiness(await bootstrap({ history }))).code, 503);
  });
}

test("dependency failure stays not-ready", async () => {
  const result = await bootstrap({ dependencyFailure: true });
  assert.equal((await readiness(result)).code, 503);
});

test("database errors return a safe readiness body and do not log credentials", async () => {
  const result = await bootstrap({ databaseFailure: true });
  const response = await readiness(result);
  assert.equal(response.code, 503);
  assert.equal(JSON.stringify(response.body), '{"status":"not_ready"}');
  assert.deepEqual(result.errors, []);
});

test("missing reviewed migration assets fail startup closed", async () => {
  const result = await bootstrap({ files: [] });
  assert.equal(result.exitCode, 1);
  assert.deepEqual(result.errors, ["Control-plane container startup failed"]);
});

for (const issuer of ["http://outside.test:18081", "http://127.0.0.1", "https://127.0.0.1:18081"]) {
  test(`container bridge refuses an unexpected issuer boundary: ${issuer}`, async () => {
    const result = await bootstrap({ issuer });
    assert.equal(result.exitCode, 1);
    assert.equal(result.listener, undefined);
  });
}
