FROM node:20-alpine
WORKDIR /app
COPY . .
RUN corepack enable && pnpm install --no-frozen-lockfile
WORKDIR /app/apps/web
CMD ["pnpm", "dev", "--host", "0.0.0.0"]
