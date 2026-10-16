import { spawn } from "node:child_process";

/** Owns only children spawned by this runner, never the Docker daemon. */
export class ProcessLifecycle {
  #active;
  #controller = new AbortController();
  #handlers;
  #exitCode;

  constructor() {
    this.#handlers = Object.fromEntries(
      ["SIGINT", "SIGTERM"].map((signal) => [
        signal,
        () => {
          if (this.#exitCode) return;
          this.#exitCode = signal === "SIGINT" ? 130 : 143;
          this.#controller.abort();
          this.#active?.();
        },
      ]),
    );
    for (const [signal, handler] of Object.entries(this.#handlers)) process.on(signal, handler);
  }

  get exitCode() {
    return this.#exitCode;
  }
  get signal() {
    return this.#controller.signal;
  }
  check() {
    this.signal.throwIfAborted();
  }
  close() {
    for (const [signal, handler] of Object.entries(this.#handlers)) process.off(signal, handler);
  }

  async run(command, args, { cwd, env, cleanup = false, timeout } = {}) {
    if (!cleanup) this.check();
    const child = spawn(command, args, {
      cwd,
      env,
      stdio: "inherit",
      // A separate POSIX group lets cancellation reach our CLI's descendants,
      // but cannot signal the caller, another worktree or a shared Docker daemon.
      detached: process.platform !== "win32",
      windowsHide: true,
    });
    let termination;
    let escalation;
    let expired = false;
    const stop = () => {
      if (termination || !child.pid) return;
      termination = terminateTree(child, "SIGTERM");
      escalation = setTimeout(() => {
        void terminateTree(child, "SIGKILL");
      }, 3000);
      escalation.unref();
    };
    if (!cleanup) this.#active = stop;
    const timer =
      timeout &&
      setTimeout(() => {
        expired = true;
        stop();
      }, timeout);
    timer?.unref();
    try {
      const result = await new Promise((resolve, reject) => {
        child.once("error", reject);
        child.once("close", (code, signal) => resolve({ code, signal }));
      });
      // A cancelled `up` must finish (including its owned process tree) BEFORE
      // finally starts `down`; no background startup can race after cleanup.
      await termination;
      if (termination && process.platform !== "win32") await terminateTree(child, "SIGKILL");
      if (!cleanup) this.check();
      if (expired) throw new Error(`${command} timed out`);
      if (result.code !== 0)
        throw new Error(`${command} ${args.join(" ")} exited ${result.code ?? result.signal}`);
    } finally {
      clearTimeout(timer);
      clearTimeout(escalation);
      if (!cleanup) this.#active = undefined;
    }
  }
}

async function terminateTree(child, signal) {
  if (process.platform !== "win32") {
    try {
      process.kill(-child.pid, signal);
    } catch (error) {
      if (error.code !== "ESRCH") throw error;
    }
    return;
  }
  // Windows signals forcibly terminate only the immediate process. taskkill /T
  // is scoped to the exact child PID so its Compose/Playwright descendants stop.
  await new Promise((resolve) => {
    const killer = spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    });
    const timer = setTimeout(() => killer.kill(), 5000);
    killer.once("error", () => {
      clearTimeout(timer);
      resolve();
    });
    killer.once("close", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}
