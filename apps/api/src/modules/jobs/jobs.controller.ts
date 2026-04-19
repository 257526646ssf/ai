import { Body, Controller, Get, Param, Post } from "@nestjs/common";
import { Roles } from "../../common/auth/roles.decorator";
import { CreateJobDto } from "./dto";
import { JobsService } from "./jobs.service";

@Controller("jobs")
export class JobsController {
  constructor(private readonly jobsService: JobsService) {}

  @Post()
  @Roles("owner", "tester")
  create(@Body() body: CreateJobDto) {
    return this.jobsService.create(body);
  }

  @Get(":jobId")
  get(@Param("jobId") jobId: string) {
    return this.jobsService.get(jobId);
  }
}
