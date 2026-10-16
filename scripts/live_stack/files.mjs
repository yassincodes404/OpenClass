import { chmod, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

/** Only this checked-in public LOCAL fixture is shared with the container UID. */
export async function writePublicRealm(directory, realm) {
  await mkdir(directory, { mode: 0o755 });
  await chmod(directory, 0o755);
  const filename = path.join(directory, "openclass-local-realm.json");
  await writeFile(filename, JSON.stringify(realm), { mode: 0o644, flag: "wx" });
  // A restrictive caller umask must not make the bind-mounted fixture unreadable.
  await chmod(filename, 0o644);
}

export async function writePrivateFile(filename, content) {
  await writeFile(filename, content, { mode: 0o600, flag: "wx" });
}
