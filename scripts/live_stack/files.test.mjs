import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { writePrivateFile, writePublicRealm } from "./files.mjs";

test("local Keycloak fixture permits both supported frontend origins", async () => {
  const realm = JSON.parse(
    await readFile(
      new URL("../../services/control-plane/keycloak/openclass-local-realm.json", import.meta.url),
      "utf8",
    ),
  );
  const client = realm.clients.find((item) => item.clientId === "openclass-portal");
  assert.ok(client);
  assert.deepEqual(client.redirectUris, ["http://127.0.0.1:5173/*", "http://127.0.0.1:3000/*"]);
  assert.deepEqual(client.webOrigins, ["http://127.0.0.1:5173", "http://127.0.0.1:3000"]);
});

test("writes only the public realm as container-readable data", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "openclass-realm-test-"));
  try {
    await writePublicRealm(path.join(directory, "realm"), { realm: "public-local-fixture" });
    assert.deepEqual(
      JSON.parse(await readFile(path.join(directory, "realm/openclass-local-realm.json"))),
      { realm: "public-local-fixture" },
    );
  } finally {
    await rm(directory, { recursive: true });
  }
});

test(
  "POSIX: restrictive umask does not hide the public mount from another UID; private files stay 0600",
  { skip: process.platform === "win32" },
  async () => {
    const directory = await mkdtemp(path.join(os.tmpdir(), "openclass-realm-mode-test-"));
    const mask = process.umask(0o077);
    try {
      const realmDirectory = path.join(directory, "realm");
      await writePublicRealm(realmDirectory, { realm: "public-local-fixture" });
      await writePrivateFile(path.join(directory, "compose.env"), "# no credentials\n");
      await writePrivateFile(path.join(directory, "manifest.json"), "{}");
      const mode = async (filename) => (await stat(filename)).mode & 0o777;
      // Kernel filesystem metadata, not a source-code regex. The mounted root
      // needs other-user traversal and the public file needs other-user read.
      assert.equal(await mode(realmDirectory), 0o755);
      assert.equal(await mode(path.join(realmDirectory, "openclass-local-realm.json")), 0o644);
      assert.equal(await mode(directory), 0o700);
      assert.equal(await mode(path.join(directory, "compose.env")), 0o600);
      assert.equal(await mode(path.join(directory, "manifest.json")), 0o600);
    } finally {
      process.umask(mask);
      await rm(directory, { recursive: true });
    }
  },
);
