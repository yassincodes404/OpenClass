# docker

The root Dockerfile and docker-compose.yml provide the Genesis engine stack.
The base is the loopback-only, no-key mock demo. Explicitly loading
`docker/full-stack.compose.yml` with the `full-stack` profile adds the
authenticated control plane, Keycloak, portal and standalone Next.js web, and
requires a private engine token before any services start. See
[full-stack development](../docs/guides/full-stack-development.md) for isolated
build/browser verification, migration ordering, local-only credentials, ports
and cleanup. Image-specific transport configuration lives here.
