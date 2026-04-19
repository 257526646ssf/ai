FROM mcr.microsoft.com/playwright:v1.48.1-jammy
WORKDIR /app
COPY . .
RUN corepack enable && pnpm install --no-frozen-lockfile
WORKDIR /app/services/runner
RUN pnpm build
CMD ["pnpm", "start"]
