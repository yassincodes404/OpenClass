import { randomBytes } from "node:crypto";
import { mkdtemp, readFile } from "node:fs/promises";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { writePrivateFile, writePublicRealm } from "./files.mjs";
import { ProcessLifecycle } from "./processes.mjs";

const root = fileURLToPath(new URL("../../", import.meta.url));
const keep = process.argv.includes("--keep");
const buildOnly = process.argv.includes("--build-only");
const engineOnly = process.argv.includes("--engine-only");
const lifecycle = new ProcessLifecycle();
const reservations = [];

// Reserve all requested loopback ports together. Docker performs the final
// atomic bind; a race fails closed instead of displacing another listener.
async function port(preferred) {
  const server = net.createServer();
  const listen = (number) =>
    new Promise((resolve, reject) => {
      server.once("error", reject);
      server.listen(number, "127.0.0.1", resolve);
    });
  try {
    await listen(preferred);
  } catch {
    server.removeAllListeners("error");
    await listen(0);
  }
  reservations.push(server);
  return server.address().port;
}
async function releasePorts() {
  for (const server of reservations)
    if (server.listening) await new Promise((resolve) => server.close(resolve));
}
async function check(url, expected = 200) {
  const response = await fetch(url, {
    signal: AbortSignal.any([lifecycle.signal, AbortSignal.timeout(10000)]),
  });
  if (response.status !== expected) throw new Error(`${url} returned ${response.status}`);
}

let started = false;
let manifestPath;
let compose;
let env;
try {
  const directory = await mkdtemp(path.join(os.tmpdir(), "openclass-live-"));
  const project = `openclass-live-${randomBytes(6).toString("hex")}`;
  manifestPath = path.join(directory, "manifest.json");
  const ports = {
    database: await port(55436),
    engine: await port(17332),
    control: await port(17333),
    portal: await port(17334),
    web: await port(17335),
    identity: await port(18081),
  };
  const urls = {
    engine: `http://127.0.0.1:${ports.engine}`,
    control: `http://127.0.0.1:${ports.control}`,
    portal: `http://127.0.0.1:${ports.portal}`,
    web: `http://127.0.0.1:${ports.web}`,
    identity: `http://127.0.0.1:${ports.identity}`,
  };
  lifecycle.check();
  const realmDirectory = path.join(directory, "realm");
  const realm = JSON.parse(
    await readFile(path.join(root, "services/control-plane/keycloak/openclass-local-realm.json")),
  );
  realm.clients[0].redirectUris = [`${urls.portal}/*`, `${urls.web}/*`];
  realm.clients[0].webOrigins = [urls.portal, urls.web];
  await writePublicRealm(realmDirectory, realm);
  const envFile = path.join(directory, "compose.env");
  await writePrivateFile(envFile, "# Intentionally empty; never load the checkout .env.\n");
  const overlay = path.join(root, "docker/full-stack.compose.yml");
  env = {
    ...process.env,
    COMPOSE_PARALLEL_LIMIT: "1",
    COMPOSE_PROFILES: "",
    OPENCLASS_DB_PORT: String(ports.database),
    OPENCLASS_PORT: String(ports.engine),
    CONTROL_PLANE_PORT: String(ports.control),
    PORTAL_PORT: String(ports.portal),
    WEB_PORT: String(ports.web),
    KEYCLOAK_PORT: String(ports.identity),
    OPENCLASS_KEYCLOAK_REALM_DIR: realmDirectory.replaceAll("\\", "/"),
    OPENCLASS_DB_PASSWORD: randomBytes(24).toString("hex"),
    OPENCLASS_AUTH_REQUIRED: "true",
    OPENCLASS_INTERNAL_TOKEN: randomBytes(32).toString("hex"),
    OPENCLASS_DECISION_PROVIDER: "mock",
    KEYCLOAK_ADMIN: "local-test-admin",
    KEYCLOAK_ADMIN_PASSWORD: randomBytes(24).toString("hex"),
    OPENCLASS_LIVE_BACKEND: "1",
    OPENCLASS_LIVE_BASE_URL: urls.portal,
    OPENCLASS_LIVE_ENGINE_URL: urls.engine,
    OPENCLASS_LIVE_CONTROL_URL: urls.control,
    OPENCLASS_LIVE_WEB_URL: urls.web,
    OPENCLASS_LIVE_IDENTITY_URL: urls.identity,
    OPENCLASS_LIVE_COMPOSE_PROJECT: project,
    OPENCLASS_LIVE_COMPOSE_ENV_FILE: envFile,
    OPENCLASS_LIVE_COMPOSE_ROOT: root,
    OPENCLASS_LIVE_COMPOSE_FILE: path.join(root, "docker-compose.yml"),
    OPENCLASS_LIVE_COMPOSE_OVERLAY: overlay,
  };
  compose = [
    "compose",
    "--project-directory",
    root,
    "--file",
    path.join(root, "docker-compose.yml"),
    "--file",
    overlay,
    "--env-file",
    envFile,
    "--project-name",
    project,
    "--profile",
    "full-stack",
  ];
  await writePrivateFile(
    manifestPath,
    JSON.stringify(
      {
        project,
        root,
        ports,
        urls,
        envFile,
        realmDirectory,
        // No passwords, bearer tokens or internal token in this manifest.
        cleanup: `node scripts/live_stack/down.mjs "${manifestPath}"`,
      },
      null,
      2,
    ),
  );
  console.log(`Isolated stack: ${manifestPath}`);
  console.log(JSON.stringify({ project, ports, urls }));
  const run = (command, args, options) =>
    lifecycle.run(command, args, { cwd: root, env, ...options });
  await run("docker", ["version", "--format", "{{.Server.Version}}"]);
  await run("docker", [
    ...compose,
    "build",
    ...(engineOnly ? ["server", "web"] : ["server", "control-plane", "portal", "web"]),
  ]);
  if (!buildOnly) {
    const controlPackage = JSON.parse(
      await readFile(path.join(root, "services/control-plane/package.json")),
    );
    if (!engineOnly && !controlPackage.scripts?.migrate)
      throw new Error("Integration dependency missing: @openclass/control-plane migrate");
    await releasePorts();
    lifecycle.check();
    // Set before spawning up: partially created volumes also belong to this run.
    started = true;
    await run("docker", [
      ...compose,
      "up",
      "-d",
      "--wait",
      "--wait-timeout",
      "240",
      ...(engineOnly ? ["server", "web", "keycloak"] : []),
    ]);
    await Promise.all([
      check(`${urls.engine}/health/ready`),
      check(`${urls.web}/health/ready`),
      check(`${urls.identity}/realms/openclass-local/.well-known/openid-configuration`),
      check(`${urls.engine}/api/v1/projects`, 401),
      check(`${urls.web}/api/v1/projects`, 401),
      ...(engineOnly
        ? []
        : [
            check(`${urls.control}/health/ready`),
            check(`${urls.portal}/health/ready`),
            check(`${urls.control}/control/workspaces`, 401),
          ]),
    ]);
    await run("docker", [
      ...compose,
      "exec",
      "-T",
      "server",
      "python",
      "-m",
      "scripts.live_stack.engine_smoke",
    ]);
    await run(process.execPath, [
      path.join(root, "node_modules/@playwright/test/cli.js"),
      "test",
      "--project=live-backend",
      ...(engineOnly ? ["--grep=standalone web"] : []),
    ]);
  }
} catch (error) {
  if (!lifecycle.exitCode) console.error(error.message);
  process.exitCode = lifecycle.exitCode ?? 1;
  if (started) {
    // Failure evidence: bounded service logs from the still-running stack,
    // before teardown. Service logs never contain secrets; the env file and
    // manifest are never printed.
    try {
      await lifecycle.run("docker", [...compose, "logs", "--no-color", "--tail=400"], {
        cwd: root,
        env,
        cleanup: true,
        timeout: 60000,
      });
    } catch {
      console.error("Could not capture stack logs after failure");
    }
  }
} finally {
  await releasePorts();
  // Signal handlers only cancel the active child. Cleanup occurs here exactly
  // once, after startup/testing has stopped, including partial failed startup.
  if (started && !keep) {
    try {
      await lifecycle.run("docker", [...compose, "down", "--volumes"], {
        cwd: root,
        env,
        cleanup: true,
        timeout: 30000,
      });
    } catch (error) {
      console.error(error.message);
      process.exitCode = lifecycle.exitCode ?? 1;
    }
  }
  if (lifecycle.exitCode) process.exitCode = lifecycle.exitCode;
  lifecycle.close();
  console.log(
    keep && started ? `Kept isolated stack; cleanup: ${manifestPath}` : "Own stack stopped.",
  );
}
