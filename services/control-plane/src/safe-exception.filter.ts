import { Catch, HttpException, Logger } from "@nestjs/common";
import type { ArgumentsHost, ExceptionFilter } from "@nestjs/common";
import { requestContext } from "./request-context.js";

@Catch()
export class SafeExceptionFilter implements ExceptionFilter {
  private readonly logger = new Logger(SafeExceptionFilter.name);

  catch(error: unknown, host: ArgumentsHost): void {
    const response = host.switchToHttp().getResponse<{
      status(code: number): { json(body: unknown): void };
    }>();
    const status = error instanceof HttpException ? error.getStatus() : 500;
    const id = requestContext.getStore()?.correlationId ?? null;
    this.logger.warn({
      event: "control.request_failed",
      code: status >= 500 ? "request_failed" : "request_rejected",
      status,
      correlation_id: id,
    });
    response.status(status).json({
      statusCode: status,
      // Do not trust even HttpException bodies from providers or database adapters.
      message: status >= 500 ? "Control-plane request failed" : this.message(status),
      correlation_id: id,
    });
  }

  private message(status: number): string {
    return (
      (
        {
          400: "Invalid request",
          401: "Authentication required",
          403: "Access denied",
          404: "Resource not found",
          409: "Request conflicts with existing state",
          413: "Request exceeds size limits",
          429: "Rate limit exceeded",
        } as Record<number, string>
      )[status] ?? "Request rejected"
    );
  }
}
