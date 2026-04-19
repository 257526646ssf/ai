import { Body, Controller, Get, Param, Post } from "@nestjs/common";
import { Roles } from "../../common/auth/roles.decorator";
import { CreateAssetDto } from "./dto";
import { AssetsService } from "./assets.service";

@Controller("projects/:id/assets")
export class AssetsController {
  constructor(private readonly assetsService: AssetsService) {}

  @Post()
  @Roles("owner", "tester")
  create(@Param("id") projectId: string, @Body() body: CreateAssetDto) {
    return this.assetsService.create(projectId, body);
  }

  @Get()
  list(@Param("id") projectId: string) {
    return this.assetsService.list(projectId);
  }
}
