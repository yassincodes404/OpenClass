FROM node:22-bookworm-slim AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@11.24.0 --activate
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/portal/package.json apps/portal/package.json
COPY apps/web/package.json apps/web/package.json
COPY packages/sdk-typescript/package.json packages/sdk-typescript/package.json
COPY services/control-plane/package.json services/control-plane/package.json
RUN pnpm --filter @openclass/portal... install --frozen-lockfile
COPY packages/sdk-typescript packages/sdk-typescript
COPY apps/portal apps/portal
ARG KEYCLOAK_PUBLIC_URL=http://127.0.0.1:8080
ENV VITE_KEYCLOAK_URL=$KEYCLOAK_PUBLIC_URL
RUN pnpm --filter @openclass/portal build

FROM nginxinc/nginx-unprivileged:1.28-alpine AS runtime
COPY docker/portal.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/portal/dist /usr/share/nginx/html
USER 101
EXPOSE 8080
