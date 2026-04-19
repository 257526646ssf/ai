import { CallHandler, ExecutionContext, Injectable, NestInterceptor, Logger } from "@nestjs/common";
import { Observable, tap } from "rxjs";

@Injectable()
export class AuditInterceptor implements NestInterceptor {
  private readonly logger = new Logger(AuditInterceptor.name);

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const req = context.switchToHttp().getRequest();
    const startedAt = Date.now();

    return next.handle().pipe(
      tap(() => {
        const duration = Date.now() - startedAt;
        this.logger.log(
          JSON.stringify({
            event: "audit",
            method: req.method,
            path: req.path,
            user: req.user?.sub || "anonymous",
            role: req.user?.role || "anonymous",
            ip: req.ip,
            durationMs: duration,
            timestamp: new Date().toISOString(),
          }),
        );
      }),
    );
  }
}
