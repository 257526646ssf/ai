import { Injectable } from "@nestjs/common";
import { PrismaService } from "../../infra/prisma.service";
import { JobsService } from "../jobs/jobs.service";
import { CreateAssetDto } from "./dto";

@Injectable()
export class AssetsService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly jobsService: JobsService,
  ) {}

  async create(projectId: string, input: CreateAssetDto) {
    const asset = await this.prisma.requirementAsset.create({
      data: {
        projectId,
        type: input.type,
        filename: input.filename,
        originalPath: input.originalPath,
      },
    });

    const job = await this.jobsService.create({
      type: "asset.parse",
      payload: { projectId, assetId: asset.id, assetType: asset.type, path: asset.originalPath },
    });

    return { asset, parseJobId: job.id };
  }

  list(projectId: string) {
    return this.prisma.requirementAsset.findMany({ where: { projectId }, orderBy: { createdAt: "desc" } });
  }
}
