import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, writeFile, unlink, rmdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../../", import.meta.url));
const command = fileURLToPath(new URL("./down.mjs", import.meta.url));

test("cleanup rejects a non-generated manifest path before invoking Docker", () => {
  const result = spawnSync(process.execPath, [command, path.join(root, "package.json")], {
    encoding: "utf8",
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Cleanup requires the generated temporary manifest/);
});

for (const project of [
  "openclass",
  "openclass-takeover-checkpoint",
  "openclass-takeover-pg17-20261015",
]) {
  test(`cleanup cannot target protected project: ${project}`, async () => {
    await rejectedManifest({ project }, /Refusing cleanup outside a generated live-test project/);
  });
}

test("cleanup rejects a different checkout", async () => {
  await rejectedManifest(
    { root: path.dirname(root) },
    /Manifest does not belong to this checkout's generated stack/,
  );
});

test("cleanup rejects an environment file outside its generated directory", async () => {
  await rejectedManifest(
    { envFile: path.join(root, ".env") },
    /Manifest does not belong to this checkout's generated stack/,
  );
});

async function rejectedManifest(overrides, expected) {
  const directory = await mkdtemp(path.join(os.tmpdir(), "openclass-live-cleanup"));
  const filename = path.join(directory, "manifest.json");
  try {
    await writeFile(
      filename,
      JSON.stringify({
        root,
        project: "openclass-live-0123456789ab",
        envFile: path.join(directory, "compose.env"),
        realmDirectory: path.join(directory, "realm"),
        ...overrides,
      }),
    );
    const result = spawnSync(process.execPath, [command, filename], { encoding: "utf8" });
    assert.equal(result.status, 1);
    assert.match(result.stderr, expected);
  } finally {
    // Only this test's known generated file and now-empty directory.
    await unlink(filename);
    await rmdir(directory);
  }
}
