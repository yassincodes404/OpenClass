import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const runnerPath = fileURLToPath(new URL("./run.mjs", import.meta.url));
const probe = new URL("./fixtures/runner-probe.mjs", import.meta.url).href;

for (const scenario of [
  { phase: "browser", signal: "SIGINT", code: 130, cleanups: 1 },
  { phase: "up", signal: "SIGTERM", code: 143, cleanups: 1 },
  { phase: "build", signal: "SIGINT", code: 130, cleanups: 0 },
  { phase: "browser", signal: "SIGTERM", code: 143, cleanups: 0, keep: true },
  { phase: "up", signal: "SIGTERM", code: 143, cleanups: 1, ignoreTerm: true },
  { phase: "up", signal: "SIGINT", code: 130, cleanups: 1, duplicate: true },
]) {
  test(
    `actual runner interruption: ${scenario.phase}/${scenario.signal}${scenario.keep ? "/keep" : ""}${scenario.ignoreTerm ? "/force" : ""}${scenario.duplicate ? "/twice" : ""}`,
    { timeout: 15000 },
    async () => {
      const directory = await mkdtemp(path.join(os.tmpdir(), "openclass-interrupt-test-"));
      const log = path.join(directory, "events.jsonl");
      await writeFile(log, "", { mode: 0o600 });
      let output = "";
      let errors = "";
      const child = spawn(
        process.execPath,
        ["--import", probe, runnerPath, ...(scenario.keep ? ["--keep"] : [])],
        {
          env: {
            ...process.env,
            RUNNER_PROBE_LOG: log,
            RUNNER_PROBE_PAUSE: scenario.phase,
            RUNNER_PROBE_IGNORE_TERM: scenario.ignoreTerm ? "1" : "",
          },
          stdio: ["ignore", "pipe", "pipe", "ipc"],
        },
      );
      child.stdout.on("data", (data) => (output += data));
      child.stderr.on("data", (data) => (errors += data));
      const ended = new Promise((resolve) => child.once("close", (code) => resolve(code)));
      const deadlineTimer = setTimeout(() => child.kill("SIGKILL"), 10000);
      const events = async () =>
        (await readFile(log, "utf8"))
          .trim()
          .split("\n")
          .filter(Boolean)
          .map((line) => JSON.parse(line));
      let paused;
      try {
        const deadline = Date.now() + 7000;
        while (Date.now() < deadline) {
          paused = (await events()).find(
            (event) => event.event === "paused" && event.phase === scenario.phase,
          );
          if (paused) break;
          await new Promise((resolve) => setTimeout(resolve, 20));
        }
        assert.ok(paused, `Runner did not reach ${scenario.phase}: ${errors}`);
        if (process.platform === "win32") child.send({ signal: scenario.signal });
        else child.kill(scenario.signal);
        if (scenario.duplicate) {
          await new Promise((resolve) => setTimeout(resolve, 5));
          if (process.platform === "win32") child.send({ signal: "SIGTERM" });
          else child.kill("SIGTERM");
        }
        const code = await ended;
        assert.equal(code, scenario.code, errors);
        const history = await events();
        const cleanups = history.filter(
          (event) => event.event === "spawn" && event.phase === "down",
        );
        assert.equal(cleanups.length, scenario.cleanups);
        const startup = history.find((event) => event.event === "spawn" && event.phase === "up");
        if (startup && cleanups.length) {
          const projectOf = (event) => event.args[event.args.indexOf("--project-name") + 1];
          assert.match(projectOf(startup), /^openclass-live-[a-f0-9]{12}$/);
          assert.equal(projectOf(cleanups[0]), projectOf(startup));
          assert.ok(
            startup.args.some((arg) =>
              arg.replaceAll("\\", "/").endsWith("/docker/full-stack.compose.yml"),
            ),
          );
          assert.deepEqual(
            cleanups[0].args.slice(0, cleanups[0].args.indexOf("down")),
            startup.args.slice(0, startup.args.indexOf("up")),
            "Cleanup must use the exact startup project, files, profile and environment file",
          );
          if (process.platform !== "win32" && !scenario.ignoreTerm) {
            assert.ok(
              history.findIndex((event) => event.event === "stopped") <
                history.findIndex((event) => event.event === "spawn" && event.phase === "down"),
              "Cleanup raced ahead of active startup/test child exit",
            );
          }
        }
        if (scenario.phase === "build") assert.equal(startup, undefined);
        assert.ok(
          history.every((event) => event.event !== "spawn" || event.authRequired === "true"),
        );
        assert.ok(history.every((event) => event.event !== "spawn" || event.strongToken));
        assert.equal(
          history.filter((event) => event.event === "spawn" && event.phase === "up").length,
          scenario.phase === "build" ? 0 : 1,
        );
        assert.throws(() => process.kill(paused.pid, 0), "Interrupted owned child is still alive");
      } finally {
        clearTimeout(deadlineTimer);
        if (child.exitCode === null) child.kill("SIGKILL");
        if (paused) {
          try {
            process.kill(paused.pid, 0);
            if (process.platform === "win32")
              spawnSync("taskkill", ["/PID", String(paused.pid), "/T", "/F"], {
                stdio: "ignore",
                timeout: 5000,
              });
            else process.kill(-paused.pid, "SIGKILL");
          } catch {
            // The runner normally already reaped this exact owned probe child.
          }
        }
        // Only remove this probe's generated temporary metadata, never a volume.
        const manifest = output.match(/Isolated stack: (.+)\r?\n/)?.[1]?.trim();
        if (manifest) await rm(path.dirname(manifest), { recursive: true });
        await rm(directory, { recursive: true });
      }
    },
  );
}
