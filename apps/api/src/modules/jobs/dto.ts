import { IsIn, IsObject, IsOptional } from "class-validator";

export class CreateJobDto {
  @IsIn(["asset.parse", "testcase.generate", "execution.run", "report.build"])
  type!: "asset.parse" | "testcase.generate" | "execution.run" | "report.build";

  @IsObject()
  payload!: Record<string, unknown>;

  @IsOptional()
  @IsObject()
  options?: Record<string, unknown>;
}
