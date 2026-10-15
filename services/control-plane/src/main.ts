import "reflect-metadata";
import { NestFactory } from "@nestjs/core";
import { ConsoleLogger } from "@nestjs/common";
import type { NestExpressApplication } from "@nestjs/platform-express";
import { AppModule } from "./app.module.js";
import { correlationMiddleware } from "./request-context.js";

async function bootstrap() {
  const app = await NestFactory.create<NestExpressApplication>(AppModule, {
    logger: new ConsoleLogger({ json: true }),
  });
  app.use(correlationMiddleware);
  app.useBodyParser("json", { limit: "5mb" });
  app.enableCors({ origin: "http://127.0.0.1:5173" });
  await app.listen(process.env.PORT ?? 7400, "127.0.0.1");
}
void bootstrap();
