FROM node:22-bookworm-slim AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@11.24.0 --activate
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/portal/package.json apps/portal/package.json
COPY apps/web/package.json apps/web/package.json
COPY packages/sdk-typescript/package.json packages/sdk-typescript/package.json
COPY services/control-plane/package.json services/control-plane/package.json
RUN pnpm --filter @openclass/web... install --frozen-lockfile
COPY packages/sdk-typescript packages/sdk-typescript
COPY apps/web apps/web
# Rewrites are serialized at build time. Never embed the internal token in Next.
ENV OPENCLASS_SERVER_URL=http://server:7331 NEXT_TELEMETRY_DISABLED=1
ENV NODE_OPTIONS=--max-old-space-size=1024 CIRCLE_NODE_TOTAL=3
RUN pnpm --filter @openclass/web build

FROM node:22-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /app/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /app/apps/web/.next/static ./apps/web/.next/static
USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
