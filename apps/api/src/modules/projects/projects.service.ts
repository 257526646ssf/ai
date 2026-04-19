import { Injectable } from "@nestjs/common";
import { PrismaService } from "../../infra/prisma.service";
import { CreateProjectDto } from "./dto";

@Injectable()
export class ProjectsService {
  constructor(private readonly prisma: PrismaService) {}

  create(input: CreateProjectDto) {
    return this.prisma.project.create({ data: input });
  }

  list() {
    return this.prisma.project.findMany({ orderBy: { createdAt: "desc" } });
  }

  get(id: string) {
    return this.prisma.project.findUnique({ where: { id } });
  }
}
