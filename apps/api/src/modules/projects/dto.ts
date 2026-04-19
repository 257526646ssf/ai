import { IsOptional, IsString, MaxLength, MinLength } from "class-validator";

export class CreateProjectDto {
  @IsString()
  @MinLength(2)
  @MaxLength(50)
  name!: string;

  @IsString()
  @IsOptional()
  @MaxLength(500)
  description?: string;

  @IsString()
  baseUrl!: string;
}
