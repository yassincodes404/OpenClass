import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";

const filename = path.resolve(process.argv[2] ?? "");
const temporaryRoot = path.resolve(os.tmpdir()) + path.sep;
if (!filename.startsWith(temporaryRoot) || path.basename(filename) !== "manifest.json")
  throw new Error("Cleanup requires the generated temporary manifest");
const manifest = JSON.parse(await readFile(filename));
const root = fileURLToPath(new URL("../../", import.meta.url));
const directory = path.dirname(filename);
if (
  path.resolve(manifest.root) !== path.resolve(root) ||
  !/^openclass-live-[A-Za-z0-9]+$/.test(path.basename(directory)) ||
  path.resolve(manifest.envFile) !== path.join(directory, "compose.env") ||
  path.resolve(manifest.realmDirectory) !== path.join(directory, "realm")
)
  throw new Error("Manifest does not belong to this checkout's generated stack");
if (!/^openclass-live-[a-f0-9]{12}$/.test(manifest.project))
  throw new Error("Refusing cleanup outside a generated live-test project");
const result = spawnSync(
  "docker",
  [
    "compose",
    "--project-directory",
    root,
    "--file",
    path.join(root, "docker-compose.yml"),
    "--file",
    path.join(root, "docker/full-stack.compose.yml"),
    "--env-file",
    manifest.envFile,
    "--project-name",
    manifest.project,
    "--profile",
    "full-stack",
    "down",
    "--volumes",
  ],
  {
    cwd: root,
    env: {
      ...process.env,
      COMPOSE_PROFILES: "",
      // Configuration-only placeholder: down never starts/reconfigures services.
      // The real private token is deliberately absent from the saved manifest.
      OPENCLASS_INTERNAL_TOKEN: "cleanup-only-not-an-application-credential",
      OPENCLASS_KEYCLOAK_REALM_DIR: manifest.realmDirectory.replaceAll("\\", "/"),
      OPENCLASS_DB_PORT: String(manifest.ports.database),
      OPENCLASS_PORT: String(manifest.ports.engine),
      CONTROL_PLANE_PORT: String(manifest.ports.control),
      PORTAL_PORT: String(manifest.ports.portal),
      WEB_PORT: String(manifest.ports.web),
      KEYCLOAK_PORT: String(manifest.ports.identity),
    },
    stdio: "inherit",
  },
);
process.exitCode = result.status ?? 1;
