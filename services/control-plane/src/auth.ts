import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from "@nestjs/common";
import { createRemoteJWKSet, jwtVerify } from "jose";

export type Principal = Readonly<{ subject: string; email?: string }>;

type RemoteJWKS = ReturnType<typeof createRemoteJWKSet>;
const jwksCache = new Map<string, RemoteJWKS>();

function jwksFor(issuer: string): RemoteJWKS {
  const base = issuer.replace(/\/$/, "");
  let jwks = jwksCache.get(base);
  if (!jwks) {
    jwks = createRemoteJWKSet(new URL(`${base}/protocol/openid-connect/certs`));
    jwksCache.set(base, jwks);
  }
  return jwks;
}

@Injectable()
export class KeycloakGuard implements CanActivate {
  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest<{
      headers: Record<string, string | undefined>;
      principal?: Principal;
    }>();
    const token = request.headers.authorization?.startsWith("Bearer ")
      ? request.headers.authorization.slice(7)
      : undefined;
    const issuer = process.env.KEYCLOAK_ISSUER_URL;
    const audience = process.env.KEYCLOAK_AUDIENCE ?? "openclass-portal";
    if (!token || !issuer) throw new UnauthorizedException("Authentication required");
    try {
      const { payload } = await jwtVerify(token, jwksFor(issuer), { issuer, audience });
      if (typeof payload.sub !== "string" || !payload.sub) throw new Error("missing subject");
      request.principal = {
        subject: payload.sub,
        email: typeof payload.email === "string" ? payload.email : undefined,
      };
      return true;
    } catch {
      throw new UnauthorizedException("Invalid or expired access token");
    }
  }
}
