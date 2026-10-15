import "reflect-metadata";
import { randomUUID } from "node:crypto";
import { mkdtemp, readFile, copyFile, readdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { ConflictException, Logger, type ExecutionContext } from "@nestjs/common";
import { Test } from "@nestjs/testing";
import type { NestExpressApplication } from "@nestjs/platform-express";
import { Pool } from "pg";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiKeyService } from "./api-key.service.js";
import { AuditService } from "./audit.service.js";
import { KeycloakGuard } from "./auth.js";
import { controlTransaction, transactionalPool } from "./db.js";
import { EngineClient, type EngineProject } from "./engine.js";
import { canonicalJson, IdempotencyService } from "./idempotency.service.js";
import { IngestionController } from "./ingestion.controller.js";
import { IngestionGuard, IngestionService } from "./ingestion.service.js";
import { MutationInterceptor } from "./mutation.interceptor.js";
import { ProjectController } from "./project.controller.js";
import { ProjectService } from "./project.service.js";
import { RateLimitService } from "./rate-limit.service.js";
import { correlationMiddleware, requestContext } from "./request-context.js";
import { SafeExceptionFilter } from "./safe-exception.filter.js";
import { WorkspaceController } from "./workspace.controller.js";
import { WorkspaceService } from "./workspace.service.js";

let migrate: (pool: Pool, directory?: string) => Promise<string[]>;
let migrationsDirectory: string;
const url = process.env.CONTROL_PLANE_TEST_DATABASE_URL;
if (!url) throw new Error("Explicit CONTROL_PLANE_TEST_DATABASE_URL is required");
const databaseOptions = {
  connectionString: url,
  connectionTimeoutMillis: 5_000,
  query_timeout: 10_000,
};
const admin = new Pool(databaseOptions);
const schema = `cp_test_${randomUUID().replaceAll("-", "")}`;
let schemaCreated = false;
const pool = transactionalPool(
  new Pool({
    ...databaseOptions,
    options: `-c search_path=${schema},public`,
    max: 12,
  }),
);
const idem = new IdempotencyService(pool);
const audit = new AuditService(pool);
const apiKeys = new ApiKeyService(pool);
const subject = "postgres-contract-user";
// Simulated durable engine receipts; SQL and Nest controllers below are real.
const simulatedProjects = new Map<string, EngineProject>();
const baseIdentity = {
  method: "POST",
  path: "/control/contract",
  body: { a: 1, b: [2, 3] },
  authorization: { subject, role: "owner" },
};
let workspace: string;
let app: NestExpressApplication;
let base: string;
const engine = {
  createProject: vi.fn(async (name: string, description: string) => {
    const key = requestContext.getStore()?.idempotencyKey ?? randomUUID();
    let project = simulatedProjects.get(key);
    if (!project) {
      project = {
        id: randomUUID(),
        name,
        slug: name.toLowerCase().replaceAll(" ", "-"),
        description,
      };
      simulatedProjects.set(key, project);
    }
    return project;
  }),
  ingestEvent: vi.fn(async () => ({ status: 201, body: { id: randomUUID(), deduped: false } })),
  ingestEventsBatch: vi.fn(async () => ({ status: 207, body: { items: [] } })),
  projectSummary: vi.fn(async () => ({ events: 0 })),
  request: vi.fn(async () => ({})),
} as unknown as EngineClient;

async function newWorkspace(name = `workspace-${randomUUID()}`): Promise<string> {
  const result = await pool.query(
    "INSERT INTO control_workspaces (slug, name) VALUES ($1, $1) RETURNING id",
    [name],
  );
  const id = result.rows[0].id as string;
  await pool.query(
    "INSERT INTO control_workspace_memberships (workspace_id, subject, role) VALUES ($1, $2, 'owner')",
    [id, subject],
  );
  return id;
}

async function post(route: string, key: string | undefined, body: unknown, actor = subject) {
  return fetch(`${base}${route}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-test-subject": actor,
      "x-correlation-id": "cp-postgres-contract",
      ...(key === undefined ? {} : { "idempotency-key": key }),
    },
    body: JSON.stringify(body),
  });
}

async function postWithApiKey(route: string, key: string, token: string, body: unknown) {
  return fetch(`${base}${route}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
      "idempotency-key": key,
    },
    body: JSON.stringify(body),
  });
}

beforeAll(async () => {
  const migrationUrl = pathToFileURL(path.resolve("scripts/migrate.mjs")).href;
  ({ migrate, migrationsDirectory } = await import(/* @vite-ignore */ migrationUrl));
  await admin.query(`CREATE SCHEMA ${schema}`);
  schemaCreated = true;
  // Unmanaged engine table exists before CP migrations in the same schema.
  await pool.query("CREATE TABLE observations (id text PRIMARY KEY, payload jsonb NOT NULL)");
  await pool.query("INSERT INTO observations VALUES ('engine-sentinel', '{\"preserved\":true}')");
  const results = await Promise.all([migrate(pool), migrate(pool)]);
  expect(results.map((result) => result.length).sort()).toEqual([0, 6]);
  workspace = await newWorkspace();
  const projects = new ProjectService(pool, engine, apiKeys, audit);
  const workspaces = new WorkspaceService(pool, audit);
  const ingestion = new IngestionService(pool, engine, new RateLimitService(), audit);
  // Vitest/esbuild does not emit TS design:paramtypes; production tsc does.
  Reflect.defineMetadata("design:paramtypes", [ProjectService], ProjectController);
  Reflect.defineMetadata("design:paramtypes", [WorkspaceService], WorkspaceController);
  Reflect.defineMetadata("design:paramtypes", [IngestionService], IngestionController);
  const guard = {
    canActivate(context: ExecutionContext) {
      const request = context.switchToHttp().getRequest();
      request.principal = { subject: request.headers["x-test-subject"] ?? subject };
      return true;
    },
  };
  const module = await Test.createTestingModule({
    controllers: [ProjectController, WorkspaceController, IngestionController],
    providers: [
      { provide: ProjectService, useValue: projects },
      { provide: WorkspaceService, useValue: workspaces },
      { provide: IngestionService, useValue: ingestion },
    ],
  })
    .overrideGuard(KeycloakGuard)
    .useValue(guard)
    .overrideGuard(IngestionGuard)
    .useValue(new IngestionGuard(guard as unknown as KeycloakGuard, apiKeys))
    .compile();
  app = module.createNestApplication<NestExpressApplication>({ logger: false });
  app.use(correlationMiddleware);
  app.useGlobalInterceptors(new MutationInterceptor(pool, idem));
  app.useGlobalFilters(new SafeExceptionFilter());
  await app.listen(0, "127.0.0.1");
  base = await app.getUrl();
}, 30_000);

afterAll(async () => {
  try {
    await app?.close();
    await pool.end();
    // Only a schema successfully created by this suite is disposable.
    if (schemaCreated) await admin.query(`DROP SCHEMA ${schema} CASCADE`);
  } finally {
    await admin.end();
  }
});

describe("real PostgreSQL migrations", () => {
  it("locks concurrent migrations, records checked versions and is repeatable", async () => {
    expect(await migrate(pool)).toEqual([]);
    const history = await pool.query(
      "SELECT version, checksum FROM control_schema_migrations ORDER BY version",
    );
    expect(history.rows).toHaveLength(6);
    expect(history.rows.every((row) => /^[0-9a-f]{64}$/.test(row.checksum))).toBe(true);
    expect(
      (await pool.query("SELECT payload FROM observations WHERE id = 'engine-sentinel'")).rows[0]
        .payload,
    ).toEqual({ preserved: true });
  });

  it("rejects checksum drift and missing applied files without altering history", async () => {
    const temporary = await mkdtemp(path.join(tmpdir(), "openclass-cp-migrations-"));
    try {
      const files = (await readdir(migrationsDirectory)).filter((file) =>
        /^\d{4}_[a-z0-9_]+\.sql$/.test(file),
      );
      for (const file of files)
        await copyFile(path.join(migrationsDirectory, file), path.join(temporary, file));
      const original = await readFile(path.join(temporary, files[0]), "utf8");
      await writeFile(path.join(temporary, files[0]), `${original}\n-- drift\n`);
      await expect(migrate(pool, temporary)).rejects.toThrow("checksum mismatch");
      await rm(path.join(temporary, files[0]));
      await expect(migrate(pool, temporary)).rejects.toThrow("missing");
      expect(
        (await pool.query("SELECT count(*)::int AS n FROM control_schema_migrations")).rows[0].n,
      ).toBe(6);
    } finally {
      await rm(temporary, { recursive: true, force: true });
    }
  });

  it("rolls back failing new migrations and never stamps them", async () => {
    const temporary = await mkdtemp(path.join(tmpdir(), "openclass-cp-migrations-"));
    try {
      for (const file of await readdir(migrationsDirectory)) {
        if (/^\d{4}_[a-z0-9_]+\.sql$/.test(file))
          await copyFile(path.join(migrationsDirectory, file), path.join(temporary, file));
      }
      await writeFile(
        path.join(temporary, "0007_fault_injection.sql"),
        "CREATE TABLE control_should_rollback (id int); SELECT * FROM control_missing_table;",
      );
      await expect(migrate(pool, temporary)).rejects.toThrow();
      expect(
        (await pool.query("SELECT to_regclass('control_should_rollback') AS name")).rows[0].name,
      ).toBeNull();
      expect(
        (await pool.query("SELECT count(*)::int AS n FROM control_schema_migrations")).rows[0].n,
      ).toBe(6);
    } finally {
      await rm(temporary, { recursive: true, force: true });
    }
  });

  it("preserves legacy audit/idempotency data and removes historical global slug uniqueness", async () => {
    const legacySchema = `cp_legacy_${randomUUID().replaceAll("-", "")}`;
    const legacy = new Pool({
      ...databaseOptions,
      options: `-c search_path=${legacySchema},public`,
    });
    await admin.query(`CREATE SCHEMA ${legacySchema}`);
    try {
      for (const name of [
        "0001_identity.sql",
        "0002_projects.sql",
        "0003_security.sql",
        "0004_provider_configs.sql",
      ]) {
        await legacy.query(await readFile(path.join(migrationsDirectory, name), "utf8"));
      }
      await legacy.query(
        "ALTER TABLE control_projects ADD CONSTRAINT legacy_global_slug UNIQUE (slug)",
      );
      const id = (
        await legacy.query(
          "INSERT INTO control_workspaces (slug,name) VALUES ('old','Old') RETURNING id",
        )
      ).rows[0].id;
      await legacy.query(
        "INSERT INTO control_audit_events (workspace_id, actor, action, target) VALUES ($1,'legacy','legacy.created','retained')",
        [id],
      );
      await legacy.query(
        "INSERT INTO control_idempotency_keys (workspace_id,key,response_hash,response,expires_at) VALUES ($1,'old-key','old-hash','{\"retained\":true}',now()+interval '1 day')",
        [id],
      );
      await migrate(legacy);
      expect((await legacy.query("SELECT actor, target FROM control_audit_events")).rows).toEqual([
        { actor: "legacy", target: "retained" },
      ]);
      expect(
        (await legacy.query("SELECT response, request_hash FROM control_idempotency_keys")).rows,
      ).toEqual([{ response: { retained: true }, request_hash: null }]);
      const other = (
        await legacy.query(
          "INSERT INTO control_workspaces (slug,name) VALUES ('new','New') RETURNING id",
        )
      ).rows[0].id;
      await legacy.query(
        "INSERT INTO control_projects (workspace_id, engine_project_id,slug,name) VALUES ($1,$2,'shared','Shared'),($3,$4,'shared','Shared')",
        [id, randomUUID(), other, randomUUID()],
      );
      await expect(
        legacy.query(
          "INSERT INTO control_projects (workspace_id, engine_project_id,slug,name) VALUES ($1,$2,'shared','Duplicate')",
          [id, randomUUID()],
        ),
      ).rejects.toMatchObject({ code: "23505" });
    } finally {
      await legacy.end();
      await admin.query(`DROP SCHEMA ${legacySchema} CASCADE`);
    }
  });

  it("fails upgrades on valuable duplicate slugs without deleting or partially migrating rows", async () => {
    const legacySchema = `cp_duplicate_${randomUUID().replaceAll("-", "")}`;
    const legacy = new Pool({
      ...databaseOptions,
      options: `-c search_path=${legacySchema},public`,
    });
    await admin.query(`CREATE SCHEMA ${legacySchema}`);
    try {
      for (const name of [
        "0001_identity.sql",
        "0002_projects.sql",
        "0003_security.sql",
        "0004_provider_configs.sql",
      ]) {
        await legacy.query(await readFile(path.join(migrationsDirectory, name), "utf8"));
      }
      await legacy.query(
        "ALTER TABLE control_projects DROP CONSTRAINT control_projects_workspace_id_slug_key",
      );
      const id = (
        await legacy.query(
          "INSERT INTO control_workspaces (slug,name) VALUES ('legacy','Legacy') RETURNING id",
        )
      ).rows[0].id;
      await legacy.query(
        "INSERT INTO control_projects (workspace_id,engine_project_id,slug,name) VALUES ($1,$2,'duplicate','First'),($1,$3,'duplicate','Second')",
        [id, randomUUID(), randomUUID()],
      );
      await expect(migrate(legacy)).rejects.toMatchObject({ code: "23505" });
      expect((await legacy.query("SELECT name FROM control_projects ORDER BY name")).rows).toEqual([
        { name: "First" },
        { name: "Second" },
      ]);
      expect(
        (
          await legacy.query(
            "SELECT count(*)::int AS n FROM pg_tables WHERE schemaname=$1 AND tablename='control_schema_migrations'",
            [legacySchema],
          )
        ).rows[0].n,
      ).toBe(0);
    } finally {
      await legacy.end();
      await admin.query(`DROP SCHEMA ${legacySchema} CASCADE`);
    }
  });
});

describe("real PostgreSQL reservation and atomic history", () => {
  it("executes once under concurrent identical requests and replays status/body across service restart", async () => {
    const key = randomUUID();
    const operation = vi.fn(async () => {
      await pool.query("SELECT pg_sleep(0.03)");
      await audit.record({
        workspaceId: workspace,
        actor: subject,
        action: "contract.created",
        target: key,
      });
      return { status: 201, body: { id: randomUUID() } };
    });
    const results = await Promise.all(
      Array.from({ length: 8 }, () =>
        idem.execute(`workspace:${workspace}`, key, baseIdentity, operation),
      ),
    );
    expect(operation).toHaveBeenCalledOnce();
    expect(results.every((result) => JSON.stringify(result) === JSON.stringify(results[0]))).toBe(
      true,
    );
    expect(
      await new IdempotencyService(pool).execute(
        `workspace:${workspace}`,
        key,
        baseIdentity,
        operation,
      ),
    ).toEqual(results[0]);
    expect(operation).toHaveBeenCalledOnce();
    expect(
      (
        await pool.query("SELECT count(*)::int AS n FROM control_audit_events WHERE target = $1", [
          key,
        ])
      ).rows[0].n,
    ).toBe(1);
  });

  it("rejects concurrent changed bodies and changed method/path with 409 before mutation", async () => {
    const key = randomUUID();
    const operation = vi.fn(async () => ({ status: 200, body: {} }));
    const results = await Promise.allSettled([
      idem.execute("conflict", key, baseIdentity, operation),
      idem.execute("conflict", key, { ...baseIdentity, body: { changed: true } }, operation),
    ]);
    expect(results.filter((result) => result.status === "fulfilled")).toHaveLength(1);
    expect(
      (results.find((result) => result.status === "rejected") as PromiseRejectedResult).reason,
    ).toBeInstanceOf(ConflictException);
    expect(operation).toHaveBeenCalledOnce();
    const winner = (
      await pool.query(
        "SELECT request_hash FROM control_idempotency_keys WHERE scope='conflict' AND key=$1",
        [key],
      )
    ).rows[0];
    expect(winner.request_hash).toMatch(/^[0-9a-f]{64}$/);
    await expect(
      idem.execute("conflict", key, { ...baseIdentity, method: "DELETE" }, operation),
    ).rejects.toBeInstanceOf(ConflictException);
    await expect(
      idem.execute("conflict", key, { ...baseIdentity, path: "/other" }, operation),
    ).rejects.toBeInstanceOf(ConflictException);
  });

  it("refreshes expired keys, including changed identity, and survives a new pool", async () => {
    const key = randomUUID();
    await idem.execute("expiry", key, baseIdentity, async () => ({
      status: 201,
      body: { old: true },
    }));
    await pool.query(
      "UPDATE control_idempotency_keys SET expires_at = clock_timestamp()-interval '1 second' WHERE scope='expiry' AND key=$1",
      [key],
    );
    const restarted = transactionalPool(
      new Pool({ ...databaseOptions, options: `-c search_path=${schema},public` }),
    );
    try {
      const changed = { ...baseIdentity, body: { changed: true } };
      const operation = vi.fn(async () => ({ status: 207, body: { fresh: true } }));
      const service = new IdempotencyService(restarted);
      const results = await Promise.all([
        service.execute("expiry", key, changed, operation),
        service.execute("expiry", key, changed, operation),
      ]);
      expect(results).toEqual([
        { status: 207, body: { fresh: true } },
        { status: 207, body: { fresh: true } },
      ]);
      expect(operation).toHaveBeenCalledOnce();
      expect(
        (
          await pool.query(
            "SELECT count(*)::int AS n FROM control_idempotency_keys WHERE scope='expiry' AND key=$1",
            [key],
          )
        ).rows[0].n,
      ).toBe(1);
    } finally {
      await restarted.end();
    }
  });

  it("rolls back domain, audit, and reservation on failure and permits retry", async () => {
    const key = randomUUID();
    const operation = async () => {
      await pool.query("INSERT INTO control_workspaces (slug,name) VALUES ($1,'Rollback')", [key]);
      await audit.record({
        workspaceId: workspace,
        actor: subject,
        action: "contract.failed",
        target: key,
      });
      throw new Error("simulated domain failure");
    };
    await expect(idem.execute("rollback", key, baseIdentity, operation)).rejects.toThrow(
      "simulated domain failure",
    );
    expect(
      (await pool.query("SELECT count(*)::int AS n FROM control_workspaces WHERE slug=$1", [key]))
        .rows[0].n,
    ).toBe(0);
    expect(
      (
        await pool.query("SELECT count(*)::int AS n FROM control_audit_events WHERE target=$1", [
          key,
        ])
      ).rows[0].n,
    ).toBe(0);
    expect(
      (
        await pool.query(
          "SELECT count(*)::int AS n FROM control_idempotency_keys WHERE scope='rollback' AND key=$1",
          [key],
        )
      ).rows[0].n,
    ).toBe(0);
    expect(
      await idem.execute("rollback", key, baseIdentity, async () => ({
        status: 200,
        body: "retry",
      })),
    ).toEqual({ status: 200, body: "retry" });
  });

  it("allows independent workspaces and never caches key material", async () => {
    const key = randomUUID();
    const operation = vi.fn(async () => ({ status: 200, body: null }));
    await Promise.all([
      idem.execute("workspace:a", key, baseIdentity, operation),
      idem.execute("workspace:b", key, baseIdentity, operation),
    ]);
    expect(operation).toHaveBeenCalledTimes(2);
    const response = await post(
      `/control/workspaces/${workspace}/projects/${randomUUID()}/keys`,
      key,
      { scopes: ["read"] },
    );
    expect(response.status).toBe(400);
  });

  it("rejects SQL UPDATE, DELETE, TRUNCATE of audit and migration history", async () => {
    await audit.record({
      workspaceId: workspace,
      actor: subject,
      action: "contract.protected",
      target: "append-only",
    });
    for (const statement of [
      "UPDATE control_audit_events SET actor='changed'",
      "DELETE FROM control_audit_events",
      "TRUNCATE control_audit_events",
      "UPDATE control_schema_migrations SET checksum='changed'",
      "DELETE FROM control_schema_migrations",
      "TRUNCATE control_schema_migrations",
    ])
      await expect(pool.query(statement)).rejects.toMatchObject({ code: "55000" });
    await expect(
      pool.query("DELETE FROM control_workspaces WHERE id=$1", [workspace]),
    ).rejects.toMatchObject({ code: "23503" });
  });
});

describe("independent-review regressions on PostgreSQL", () => {
  it("never creates or caches one-time API keys through lower/upper/mixed-case routes", async () => {
    const created = await post(`/control/workspaces/${workspace}/projects`, randomUUID(), {
      name: "Secret Route Project",
    });
    const project = await created.json();
    const create = vi.spyOn(apiKeys, "create");
    try {
      for (const spelling of ["keys", "KEYS", "KeYs"]) {
        const key = randomUUID();
        const response = await post(
          `/control/workspaces/${workspace}/projects/${project.id}/${spelling}`,
          key,
          { scopes: ["read"] },
        );
        expect(response.status).toBe(400);
        expect(
          (
            await pool.query(
              "SELECT count(*)::int AS n FROM control_idempotency_keys WHERE key=$1",
              [key],
            )
          ).rows[0].n,
        ).toBe(0);
      }
      expect(create).not.toHaveBeenCalled();
      expect(
        (
          await pool.query("SELECT count(*)::int AS n FROM control_api_keys WHERE project_id=$1", [
            project.id,
          ])
        ).rows[0].n,
      ).toBe(0);
    } finally {
      create.mockRestore();
    }
  });

  it("conflicts rather than replaying another API key's receipt in the same project and scopes", async () => {
    const created = await post(`/control/workspaces/${workspace}/projects`, randomUUID(), {
      name: "Distinct Key Identity Project",
    });
    const project = await created.json();
    const first = await apiKeys.create(workspace, project.id, ["ingest"]);
    const second = await apiKeys.create(workspace, project.id, ["ingest"]);
    const key = randomUUID();
    const route = `/control/workspaces/${workspace}/projects/${project.id}/events`;
    const before = vi.mocked(engine.ingestEvent).mock.calls.length;
    const initial = await postWithApiKey(route, key, first.key, { content: "same ordinary input" });
    expect(initial.status).toBe(201);
    const original = await initial.json();
    expect(
      (await postWithApiKey(route, key, second.key, { content: "same ordinary input" })).status,
    ).toBe(409);
    const replay = await postWithApiKey(route, key, first.key, { content: "same ordinary input" });
    expect(replay.status).toBe(201);
    expect(await replay.json()).toEqual(original);
    expect(vi.mocked(engine.ingestEvent).mock.calls.length - before).toBe(1);
    expect(first.row.id).not.toBe(second.row.id);
  });

  it.each(["revoked", "scope-removed"])(
    "rejects %s API keys admitted by the guard while waiting for a receipt lock",
    async (change) => {
      const created = await post(`/control/workspaces/${workspace}/projects`, randomUUID(), {
        name: `Waiting Key ${change}`,
      });
      const project = await created.json();
      const credential = await apiKeys.create(workspace, project.id, ["ingest"]);
      const key = randomUUID();
      const route = `/control/workspaces/${workspace}/projects/${project.id}/events`;
      const body = { content: "guard admitted before authorization changed" };
      expect((await postWithApiKey(route, key, credential.key, body)).status).toBe(201);
      const before = vi.mocked(engine.ingestEvent).mock.calls.length;
      const receipt = (
        await pool.query(
          "SELECT response_hash FROM control_idempotency_keys WHERE scope=$1 AND key=$2",
          [`workspace:${workspace}`, key],
        )
      ).rows[0];
      const lock = await pool.connect();
      const originalVerify = apiKeys.verify.bind(apiKeys);
      let admitted!: () => void;
      const guardAdmitted = new Promise<void>((resolve) => {
        admitted = resolve;
      });
      const verify = vi.spyOn(apiKeys, "verify").mockImplementationOnce(async (...args) => {
        const result = await originalVerify(...args);
        admitted();
        return result;
      });
      let pending: Promise<Response> | undefined;
      try {
        await lock.query("BEGIN");
        await lock.query("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", [
          canonicalJson([`workspace:${workspace}`, key]),
        ]);
        pending = postWithApiKey(route, key, credential.key, body);
        await Promise.race([
          guardAdmitted,
          new Promise<never>((_, reject) => {
            const timer = setTimeout(() => reject(new Error("Guard admission timed out")), 3000);
            timer.unref();
            guardAdmitted.then(() => clearTimeout(timer));
          }),
        ]);
        if (change === "revoked") await apiKeys.revoke(project.id, credential.row.id);
        else
          await pool.query("UPDATE control_api_keys SET scopes=ARRAY['read']::text[] WHERE id=$1", [
            credential.row.id,
          ]);
        await lock.query("COMMIT");
        expect((await pending).status).toBe(403);
        expect(vi.mocked(engine.ingestEvent).mock.calls.length).toBe(before);
        expect(
          (
            await pool.query(
              "SELECT response_hash FROM control_idempotency_keys WHERE scope=$1 AND key=$2",
              [`workspace:${workspace}`, key],
            )
          ).rows[0],
        ).toEqual(receipt);
      } finally {
        await lock.query("ROLLBACK");
        lock.release();
        verify.mockRestore();
        await pending?.catch(() => undefined);
      }
    },
  );

  it("paginates all 60 audit events sharing a transaction timestamp without loss or duplicates", async () => {
    const ws = await newWorkspace();
    await controlTransaction(pool, async () => {
      for (let i = 0; i < 60; i++) {
        await audit.record({
          workspaceId: ws,
          actor: subject,
          action: "pagination.batch",
          target: `item:${i}`,
        });
      }
    });
    expect(
      (
        await pool.query(
          "SELECT count(DISTINCT created_at)::int AS n FROM control_audit_events WHERE workspace_id=$1",
          [ws],
        )
      ).rows[0].n,
    ).toBe(1);
    const first = await audit.list(ws, { limit: 50 });
    expect(first.items).toHaveLength(50);
    expect(first.next_cursor).toBeTypeOf("string");
    const second = await audit.list(ws, { limit: 50, cursor: first.next_cursor! });
    expect(second.items).toHaveLength(10);
    expect(second.next_cursor).toBeNull();
    const ids = [...first.items, ...second.items].map((item) => item.id);
    expect(new Set(ids).size).toBe(60);
    expect(ids).toEqual(
      (
        await pool.query(
          "SELECT id FROM control_audit_events WHERE workspace_id=$1 ORDER BY created_at DESC, id DESC",
          [ws],
        )
      ).rows.map((row) => row.id),
    );
  });

  it("preserves sub-millisecond PostgreSQL timestamps in the opaque seek cursor", async () => {
    const ws = await newWorkspace();
    await pool.query(
      "INSERT INTO control_audit_events (workspace_id,actor,action,target,created_at) VALUES" +
        " ($1,'fixture','pagination.precision','newer','2026-10-15T00:00:00.123456Z')," +
        " ($1,'fixture','pagination.precision','older','2026-10-15T00:00:00.123455Z')",
      [ws],
    );
    const first = await audit.list(ws, { limit: 1 });
    expect(first.items[0].target).toBe("newer");
    expect(JSON.parse(Buffer.from(first.next_cursor!, "base64url").toString("utf8")).at).toBe(
      "2026-10-15T00:00:00.123456Z",
    );
    const second = await audit.list(ws, { limit: 1, cursor: first.next_cursor! });
    expect(second.items[0].target).toBe("older");
  });
});

describe("actual controllers with PostgreSQL (engine explicitly simulated)", () => {
  it("rolls back mapping, audit and receipt after audit failure; retries reconcile the same remote receipt", async () => {
    const key = randomUUID();
    const route = `/control/workspaces/${workspace}/projects`;
    const original = audit.record.bind(audit);
    const before = simulatedProjects.size;
    const remoteRequests = vi.mocked(engine.request).mock.calls.length;
    const record = vi.spyOn(audit, "record").mockImplementationOnce(async (input) => {
      await original(input);
      throw new Error("simulated failure after audit INSERT");
    });
    try {
      const failed = await post(route, key, { name: "Rollback Controller Project" });
      expect(failed.status).toBe(500);
      expect(
        (
          await pool.query(
            "SELECT count(*)::int AS n FROM control_projects WHERE name='Rollback Controller Project'",
          )
        ).rows[0].n,
      ).toBe(0);
      expect(
        (
          await pool.query(
            "SELECT count(*)::int AS n FROM control_audit_events WHERE target='project:rollback-controller-project'",
          )
        ).rows[0].n,
      ).toBe(0);
      expect(
        (
          await pool.query("SELECT count(*)::int AS n FROM control_idempotency_keys WHERE key=$1", [
            key,
          ])
        ).rows[0].n,
      ).toBe(0);
      expect(simulatedProjects.size - before).toBe(1);
      record.mockRestore();
      const retry = await post(route, key, { name: "Rollback Controller Project" });
      expect(retry.status).toBe(201);
      const project = await retry.json();
      expect(simulatedProjects.size - before).toBe(1);
      expect(
        [...simulatedProjects.values()].some((remote) => remote.id === project.engine_project_id),
      ).toBe(true);
      expect(vi.mocked(engine.request).mock.calls.length).toBe(remoteRequests);
    } finally {
      record.mockRestore();
    }
  });

  it("creates a project once for parallel requests, preserves status and rejects changed payload", async () => {
    const route = `/control/workspaces/${workspace}/projects`;
    const key = randomUUID();
    const before = vi.mocked(engine.createProject).mock.calls.length;
    const responses = await Promise.all(
      Array.from({ length: 6 }, () =>
        post(route, key, { name: "Concurrent Project", description: "" }),
      ),
    );
    expect(responses.map((response) => response.status)).toEqual(Array(6).fill(201));
    const bodies = await Promise.all(responses.map((response) => response.json()));
    expect(bodies.every((body) => body.id === bodies[0].id)).toBe(true);
    expect(vi.mocked(engine.createProject).mock.calls.length - before).toBe(1);
    const failed = await post(route, key, { name: "Changed Project", description: "" });
    expect(failed.status).toBe(409);
    expect(failed.headers.get("x-correlation-id")).toBe("cp-postgres-contract");
    expect(
      (
        await pool.query("SELECT correlation_id FROM control_audit_events WHERE project_id=$1", [
          bodies[0].id,
        ])
      ).rows,
    ).toEqual([{ correlation_id: "cp-postgres-contract" }]);
  });

  it("rejects removed membership and changed role on replay", async () => {
    const ws = await newWorkspace();
    const route = `/control/workspaces/${ws}/projects`;
    const key = randomUUID();
    expect((await post(route, key, { name: "Authorized Project" })).status).toBe(201);
    await pool.query(
      "UPDATE control_workspace_memberships SET role='viewer' WHERE workspace_id=$1",
      [ws],
    );
    expect((await post(route, key, { name: "Authorized Project" })).status).toBe(409);
    await pool.query("DELETE FROM control_workspace_memberships WHERE workspace_id=$1", [ws]);
    expect((await post(route, key, { name: "Authorized Project" })).status).toBe(404);
  });

  it("atomically creates workspace, owner, audit and actor-scoped replay", async () => {
    const key = randomUUID();
    const responses = await Promise.all([
      post("/control/workspaces", key, { name: "Actor Scoped Workspace" }),
      post("/control/workspaces", key, { name: "Actor Scoped Workspace" }),
    ]);
    const bodies = await Promise.all(responses.map((response) => response.json()));
    expect(responses.every((response) => response.status === 201)).toBe(true);
    expect(bodies[0].id).toBe(bodies[1].id);
    expect(
      (
        await pool.query(
          "SELECT count(*)::int AS n FROM control_audit_events WHERE workspace_id=$1",
          [bodies[0].id],
        )
      ).rows[0].n,
    ).toBe(1);
  });

  it("replays ingestion once and retains status without repeating remote calls or audit", async () => {
    const projectResponse = await post(`/control/workspaces/${workspace}/projects`, randomUUID(), {
      name: "Ingestion Project",
    });
    const project = await projectResponse.json();
    const key = randomUUID();
    const route = `/control/workspaces/${workspace}/projects/${project.id}/events`;
    const before = vi.mocked(engine.ingestEvent).mock.calls.length;
    const responses = await Promise.all(
      Array.from({ length: 4 }, () => post(route, key, { content: "ordinary contract content" })),
    );
    expect(responses.map((response) => response.status)).toEqual([201, 201, 201, 201]);
    const bodies = await Promise.all(responses.map((response) => response.json()));
    expect(bodies.every((body) => body.id === bodies[0].id)).toBe(true);
    expect(vi.mocked(engine.ingestEvent).mock.calls.length - before).toBe(1);
    expect((await post(route, key, { content: "changed content" })).status).toBe(409);
    expect(
      (
        await pool.query(
          "SELECT count(*)::int AS n FROM control_audit_events WHERE action='observation.ingested' AND project_id=$1",
          [project.id],
        )
      ).rows[0].n,
    ).toBe(1);
  });

  it("never discloses database error text in HTTP failures or logs", async () => {
    const spy = vi.spyOn(Logger.prototype, "warn").mockImplementation(() => undefined);
    const sentinel = "simulated-upstream-private-detail";
    vi.mocked(engine.createProject).mockRejectedValueOnce(new Error(sentinel));
    try {
      const response = await post(`/control/workspaces/${workspace}/projects`, randomUUID(), {
        name: "Failed Project",
      });
      expect(response.status).toBe(500);
      const body = await response.text();
      expect(body).not.toContain(sentinel);
      expect(JSON.stringify(spy.mock.calls)).not.toContain(sentinel);
      expect(JSON.stringify(spy.mock.calls)).toContain("cp-postgres-contract");
    } finally {
      spy.mockRestore();
    }
  });
});
