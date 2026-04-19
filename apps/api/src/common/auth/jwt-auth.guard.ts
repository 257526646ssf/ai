import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from "@nestjs/common";
import { JwtService } from "@nestjs/jwt";

@Injectable()
export class JwtAuthGuard implements CanActivate {
  constructor(private readonly jwtService: JwtService) {}

  canActivate(context: ExecutionContext): boolean {
    const req = context.switchToHttp().getRequest();
    if (req.path?.includes("/auth/login")) {
      return true;
    }

    const authHeader = req.headers.authorization;
    if (!authHeader?.startsWith("Bearer ")) {
      throw new UnauthorizedException("Missing bearer token");
    }

    const token = authHeader.replace("Bearer ", "");

    try {
      req.user = this.jwtService.verify(token, { secret: process.env.JWT_SECRET || "dev-secret" });
      return true;
    } catch {
      throw new UnauthorizedException("Invalid token");
    }
  }
}
