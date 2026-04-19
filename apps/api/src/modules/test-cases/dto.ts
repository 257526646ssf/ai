import { IsArray, IsOptional, IsString } from "class-validator";

export class CreateTestCaseDto {
  @IsString()
  title!: string;

  @IsString()
  module!: string;

  @IsString()
  priority!: "P0" | "P1" | "P2" | "P3";

  @IsString()
  type!: "functional" | "boundary" | "exception" | "ui" | "performance" | "compatibility";

  @IsArray()
  preconditions!: string[];

  @IsArray()
  steps!: Array<Record<string, unknown>>;

  @IsArray()
  tags!: string[];

  @IsOptional()
  @IsString()
  source?: "ai" | "manual" | "imported";

  @IsOptional()
  confidence?: number;
}

export class GenerateTestCasesDto {
  @IsArray()
  assetIds!: string[];

  @IsOptional()
  options?: {
    coverageLevel?: "basic" | "standard" | "comprehensive";
    testTypes?: string[];
    focusModules?: string[];
    language?: string;
  };
}

export class UpdateTestCaseDto {
  @IsOptional()
  @IsString()
  title?: string;

  @IsOptional()
  steps?: Record<string, unknown>[] | Record<string, unknown>;
}
