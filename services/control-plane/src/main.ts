import "reflect-metadata";
import { NestFactory } from "@nestjs/core";
import { AppModule } from "./app.module.js";

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.enableCors({ origin: "http://127.0.0.1:5173" });
  await app.listen(process.env.PORT ?? 7400, "127.0.0.1");
}
void bootstrap();
