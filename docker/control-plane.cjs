// Container-only transport bootstrap. The native entry point deliberately binds
// loopback; domain/authentication logic remains in the existing AppModule.
require("reflect-metadata");
const { NestFactory } = require("@nestjs/core");
const { ConsoleLogger } = require("@nestjs/common");
const { AppModule } = require("../dist/app.module.js");
const { CONTROL_DB } = require("../dist/db.js");
const { correlationMiddleware } = require("../dist/request-context.js");
const { createHash } = require("node:crypto");
const { readdir, readFile } = require("node:fs/promises");
const path = require("node:path");
const net = require("node:net");

async function bootstrap() {
  const issuer = new URL(process.env.KEYCLOAK_ISSUER_URL);
  // The existing guard derives JWKS from the public issuer. Bridge *only*
  // container loopback to Keycloak so browser and verifier use the same issuer.
  // No token rewriting, signature bypass, host networking, or host DNS changes.
  if (process.env.KEYCLOAK_CONTAINER_HOST) {
    if (
      issuer.protocol !== "http:" ||
      issuer.hostname !== "127.0.0.1" ||
      !issuer.port ||
      Number(issuer.port) < 1024
    )
      throw new Error("Expected unprivileged loopback identity issuer");
    const bridge = net.createServer((socket) => {
      const upstream = net.connect(8080, process.env.KEYCLOAK_CONTAINER_HOST);
      socket.setTimeout(10000, () => socket.destroy());
      socket.pipe(upstream).pipe(socket);
      socket.on("error", () => upstream.destroy());
      upstream.on("error", () => socket.destroy());
      socket.on("close", () => upstream.destroy());
      upstream.on("close", () => socket.destroy());
    });
    await new Promise((resolve, reject) => {
      bridge.once("error", reject);
      bridge.listen(Number(issuer.port), "127.0.0.1", resolve);
    });
  }
  const app = await NestFactory.create(AppModule, {
    logger: new ConsoleLogger({ json: true }),
  });
  app.use(correlationMiddleware);
  app.useBodyParser("json", { limit: "5mb" });
  // Reuse AppModule's transactional pool/interceptor rather than creating a
  // separate persistence path. Readiness checks history; it never applies SQL.
  const pool = app.get(CONTROL_DB);
  const directory = path.join(__dirname, "../migrations");
  const migrations = await Promise.all(
    (await readdir(directory))
      .filter((name) => /^\d{4}_[a-z0-9_]+\.sql$/.test(name))
      .sort()
      .map(async (version) => ({
        version,
        checksum: createHash("sha256")
          .update(await readFile(path.join(directory, version), "utf8"))
          .digest("hex"),
      })),
  );
  if (!migrations.length) throw new Error("Missing reviewed control-plane migrations");
  app.getHttpAdapter().get("/health/ready", async (_request, response) => {
    try {
      const history = await pool.query(
        "SELECT version, checksum FROM control_schema_migrations ORDER BY version",
      );
      if (
        history.rows.length !== migrations.length ||
        history.rows.some(
          (row, index) =>
            row.version !== migrations[index].version ||
            row.checksum !== migrations[index].checksum,
        )
      )
        throw new Error("Control-plane migration history mismatch");
      const results = await Promise.all([
        fetch(`${process.env.ENGINE_BASE_URL}/health/ready`, { signal: AbortSignal.timeout(3000) }),
        fetch(`${issuer}/protocol/openid-connect/certs`, { signal: AbortSignal.timeout(3000) }),
      ]);
      if (results.some((result) => !result.ok)) throw new Error("Dependency not ready");
      response.status(200).json({ status: "ready" });
    } catch {
      response.status(503).json({ status: "not_ready" });
    }
  });
  app.enableShutdownHooks();
  await app.listen(Number(process.env.PORT ?? 7400), "0.0.0.0");
}
bootstrap().catch(() => {
  console.error("Control-plane container startup failed");
  process.exit(1);
});
