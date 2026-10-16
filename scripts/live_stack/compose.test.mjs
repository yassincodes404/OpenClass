import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../../", import.meta.url));
function configuration({ workspace = false, token = "" } = {}) {
  const env = { ...process.env };
  for (const key of Object.keys(env)) {
    if (/^(OPENCLASS_|COMPOSE_|CONTROL_PLANE_|KEYCLOAK_|PORTAL_|WEB_PORT)/.test(key))
      delete env[key];
  }
  // Prove that an inherited false cannot weaken the workspace override.
  if (workspace) env.OPENCLASS_AUTH_REQUIRED = "false";
  env.OPENCLASS_INTERNAL_TOKEN = token;
  return spawnSync(
    "docker",
    [
      "compose",
      "--project-directory",
      root,
      "--env-file",
      path.join(root, ".env.example"),
      "--file",
      path.join(root, "docker-compose.yml"),
      ...(workspace
        ? ["--file", path.join(root, "docker/full-stack.compose.yml"), "--profile", "full-stack"]
        : []),
      "config",
      "--format",
      "json",
    ],
    { cwd: root, env, encoding: "utf8", timeout: 15000 },
  );
}

test("base .env.example quickstart config is mock, no-key and loopback-only", () => {
  const result = configuration();
  assert.equal(result.status, 0, result.stderr);
  const { services } = JSON.parse(result.stdout);
  assert.equal(services.server.environment.OPENCLASS_AUTH_REQUIRED, "false");
  assert.equal(services.server.environment.OPENCLASS_INTERNAL_TOKEN, "");
  assert.equal(services.server.environment.OPENCLASS_DECISION_PROVIDER, "mock");
  assert.equal(services["control-plane"], undefined);
  for (const service of Object.values(services))
    for (const port of service.ports ?? []) assert.equal(port.host_ip, "127.0.0.1");
});

test("workspace config rejects a missing token before any daemon operation", () => {
  const result = configuration({ workspace: true });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Full-stack requires a private OPENCLASS_INTERNAL_TOKEN/);
});

test("workspace defaults use a separate project and database volume from the anonymous demo", () => {
  const baseResult = configuration();
  const workspaceResult = configuration({
    workspace: true,
    token: "public-test-placeholder-not-a-private-credential",
  });
  assert.equal(baseResult.status, 0, baseResult.stderr);
  assert.equal(workspaceResult.status, 0, workspaceResult.stderr);
  const base = JSON.parse(baseResult.stdout);
  const workspace = JSON.parse(workspaceResult.stdout);
  assert.notEqual(workspace.name, base.name);
  assert.notEqual(workspace.volumes["postgres-data"].name, base.volumes["postgres-data"].name);
});

test("workspace config forces auth and preserves the private engine/control-plane boundary", () => {
  const token = "public-test-placeholder-not-a-private-credential";
  const result = configuration({ workspace: true, token });
  assert.equal(result.status, 0, result.stderr);
  const { services } = JSON.parse(result.stdout);
  assert.equal(services.server.environment.OPENCLASS_AUTH_REQUIRED, "true");
  assert.equal(services.server.environment.OPENCLASS_INTERNAL_TOKEN, token);
  assert.equal(services["control-plane"].environment.OPENCLASS_INTERNAL_TOKEN, token);
  assert.ok(services["control-migrate"]);
  assert.ok(services.portal);
  assert.ok(services.web);
  assert.equal(services.web.environment.CONTROL_PLANE_URL, "http://control-plane:7400");
  assert.equal(
    services.web.build.args.KEYCLOAK_PUBLIC_URL,
    services.portal.build.args.KEYCLOAK_PUBLIC_URL,
  );
  for (const service of [services.portal, services.web]) {
    assert.equal(service.environment?.OPENCLASS_INTERNAL_TOKEN, undefined);
    assert.equal(service.build.args?.OPENCLASS_INTERNAL_TOKEN, undefined);
  }
  for (const service of Object.values(services))
    for (const port of service.ports ?? []) assert.equal(port.host_ip, "127.0.0.1");
});

test("web image includes shared workflow sources and public identity build configuration", async () => {
  const source = await readFile(path.join(root, "apps/web/Dockerfile"), "utf8");
  assert.match(source, /COPY apps\/portal\/src apps\/portal\/src/);
  assert.match(source, /--filter @openclass\/portal\.\.\./);
  assert.match(source, /ARG KEYCLOAK_PUBLIC_URL=/);
  assert.match(source, /NEXT_PUBLIC_KEYCLOAK_URL=\$KEYCLOAK_PUBLIC_URL/);
});
