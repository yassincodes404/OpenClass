// Unit-test-only inert Docker/process adapters. Never loaded by live-backend CI.
// Execute the actual runner source; do not start Docker, browsers or business APIs.
import childProcess from "node:child_process";
import { syncBuiltinESMExports } from "node:module";
import { appendFileSync } from "node:fs";

const spawn = childProcess.spawn;
const spawnSync = childProcess.spawnSync;
childProcess.spawnSync = (command, args, options) => {
  if (command === "docker")
    throw new Error(
      "Interruption probe refuses blocking Docker calls; runner must remain cancellable",
    );
  return spawnSync(command, args, options);
};
childProcess.spawn = (command, args, options) => {
  const browser = args[0]?.replaceAll("\\", "/").endsWith("@playwright/test/cli.js");
  if (command !== "docker" && !browser) return spawn(command, args, options);
  const phase = browser
    ? "browser"
    : ["version", "build", "up", "exec", "down"].find((name) => args.includes(name));
  appendFileSync(
    process.env.RUNNER_PROBE_LOG,
    JSON.stringify({
      event: "spawn",
      phase,
      args,
      authRequired: options.env.OPENCLASS_AUTH_REQUIRED,
      strongToken: options.env.OPENCLASS_INTERNAL_TOKEN?.length === 64,
    }) + "\n",
  );
  return spawn(
    process.execPath,
    [
      "-e",
      `
        const fs = require("node:fs");
        const phase = process.argv[1];
        const log = event => fs.appendFileSync(process.env.RUNNER_PROBE_LOG,
          JSON.stringify({event, phase, pid: process.pid}) + "\\n");
        if (phase === process.env.RUNNER_PROBE_PAUSE) {
          process.on("SIGTERM", () => {
            if (process.env.RUNNER_PROBE_IGNORE_TERM) return;
            setTimeout(() => { log("stopped"); process.exit(0); }, 80);
          });
          setInterval(() => {}, 1000);
          log("paused");
        } else {
          log("completed");
        }
      `,
      phase,
    ],
    options,
  );
};
syncBuiltinESMExports();
globalThis.fetch = async (url) => ({
  status: /\/api\/v1\/projects$|\/control\/workspaces$/.test(url) ? 401 : 200,
});
// Windows does not deliver POSIX signals to Node children. Exercise the same
// registered handler there; Linux tests deliver the actual OS signal instead.
process.on("message", ({ signal }) => process.emit(signal));
process.channel?.unref();
