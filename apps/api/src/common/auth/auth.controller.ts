import { Body, Controller, Post } from "@nestjs/common";
import { IsIn, IsString } from "class-validator";
import { JwtService } from "@nestjs/jwt";

class LoginDto {
  @IsString()
  userId!: string;

  @IsIn(["owner", "tester", "viewer"])
  role!: "owner" | "tester" | "viewer";
}

@Controller("auth")
export class AuthController {
  constructor(private readonly jwtService: JwtService) {}

  @Post("login")
  login(@Body() body: LoginDto) {
    const token = this.jwtService.sign(
      { sub: body.userId, role: body.role },
      { secret: process.env.JWT_SECRET || "dev-secret", expiresIn: "8h" },
    );

    return { accessToken: token };
  }
}
