FROM node:22-bookworm-slim AS workspace
WORKDIR /app
ENV COREPACK_HOME=/opt/corepack
RUN corepack enable && corepack prepare pnpm@11.24.0 --activate \
    && chmod -R a+rX /opt/corepack
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/portal/package.json apps/portal/package.json
COPY apps/web/package.json apps/web/package.json
COPY packages/sdk-typescript/package.json packages/sdk-typescript/package.json
COPY services/control-plane/package.json services/control-plane/package.json

FROM workspace AS build
RUN pnpm --filter @openclass/control-plane... install --frozen-lockfile
COPY services/control-plane services/control-plane
RUN pnpm --filter @openclass/control-plane build

# Legacy pnpm deploy re-resolves dependencies instead of honoring a frozen
# lockfile. Install the runtime graph separately to preserve locked resolution.
FROM workspace AS production-dependencies
RUN pnpm --filter @openclass/control-plane... install --prod --frozen-lockfile

FROM workspace AS runtime
COPY --from=production-dependencies --chown=node:node /app/node_modules ./node_modules
COPY --from=production-dependencies --chown=node:node /app/services/control-plane/node_modules ./services/control-plane/node_modules
COPY --from=build --chown=node:node /app/services/control-plane/dist ./services/control-plane/dist
COPY --from=build --chown=node:node /app/services/control-plane/scripts ./services/control-plane/scripts
COPY --from=build --chown=node:node /app/services/control-plane/migrations ./services/control-plane/migrations
COPY --chown=node:node docker/control-plane.cjs services/control-plane/docker/control-plane.cjs
WORKDIR /app/services/control-plane
USER node
ENV NODE_ENV=production PORT=7400
EXPOSE 7400
CMD ["node", "docker/control-plane.cjs"]
