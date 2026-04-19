import { Body, Controller, Get, Param, Post } from "@nestjs/common";
import { Roles } from "../../common/auth/roles.decorator";
import { CreateProjectDto } from "./dto";
import { ProjectsService } from "./projects.service";

@Controller("projects")
export class ProjectsController {
  constructor(private readonly projectsService: ProjectsService) {}

  @Post()
  @Roles("owner", "tester")
  create(@Body() body: CreateProjectDto) {
    return this.projectsService.create(body);
  }

  @Get()
  list() {
    return this.projectsService.list();
  }

  @Get(":id")
  get(@Param("id") id: string) {
    return this.projectsService.get(id);
  }
}
