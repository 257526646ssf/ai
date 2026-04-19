import { IsIn, IsString } from "class-validator";

export class CreateAssetDto {
  @IsIn(["prototype", "document"])
  type!: "prototype" | "document";

  @IsString()
  filename!: string;

  @IsString()
  originalPath!: string;
}
