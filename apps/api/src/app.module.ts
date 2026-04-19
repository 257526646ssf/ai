import { BullModule } from "@nestjs/bullmq";
import { Module } from "@nestjs/common";
import { APP_INTERCEPTOR } from "@nestjs/core";
import { ConfigModule, ConfigService } from "@nestjs/config";
import { PrismaService } from "./infra/prisma.service";
import { ProjectsModule } from "./modules/projects/projects.module";
import { AssetsModule } from "./modules/assets/assets.module";
import { TestCasesModule } from "./modules/test-cases/test-cases.module";
import { ExecutionsModule } from "./modules/executions/executions.module";
import { ReportsModule } from "./modules/reports/reports.module";
import { JobsModule } from "./modules/jobs/jobs.module";
import { AuthModule } from "./common/auth/auth.module";
import { EncryptionService } from "./common/encryption.service";
import { AuditInterceptor } from "./common/audit.interceptor";
import { HealthController } from "./common/health.controller";

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    AuthModule,
    BullModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (configService: ConfigService) => ({
        connection: {
          url: configService.get<string>("REDIS_URL", "redis://localhost:6379"),
        },
      }),
    }),
    ProjectsModule,
    AssetsModule,
    TestCasesModule,
    ExecutionsModule,
    ReportsModule,
    JobsModule,
  ],
  controllers: [HealthController],
  providers: [
    PrismaService,
    EncryptionService,
    { provide: APP_INTERCEPTOR, useClass: AuditInterceptor },
  ],
  exports: [PrismaService],
})
export class AppModule {}
