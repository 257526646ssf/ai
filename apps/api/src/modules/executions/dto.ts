import { IsBoolean, IsObject, IsOptional, IsString } from "class-validator";

export class ExecuteTestCaseDto {
  @IsString()
  environmentId!: string;

  @IsOptional()
  @IsObject()
  options?: {
    headless?: boolean;
    recordVideo?: boolean;
    captureScreenshots?: boolean;
    stopOnFailure?: boolean;
    dataOverride?: Record<string, unknown>;
  };
}
