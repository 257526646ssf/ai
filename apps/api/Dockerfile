FROM node:20-alpine
WORKDIR /app
COPY . .
RUN corepack enable && pnpm install --no-frozen-lockfile
WORKDIR /app/apps/api
RUN pnpm build
CMD ["pnpm", "start"]
