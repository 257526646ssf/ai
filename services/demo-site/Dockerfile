FROM node:20-alpine
WORKDIR /app
COPY . .
RUN corepack enable && pnpm install --no-frozen-lockfile
WORKDIR /app/services/demo-site
CMD ["pnpm", "start"]
