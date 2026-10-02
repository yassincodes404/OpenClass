import { generateKeyPairSync } from "node:crypto";
import type { ExecutionContext } from "@nestjs/common";
import { UnauthorizedException } from "@nestjs/common";
import { SignJWT } from "jose";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { KeycloakGuard } from "./auth.js";

const { publicKey, privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });

vi.mock("jose", async (importOriginal) => {
  const actual = await importOriginal<typeof import("jose")>();
  return { ...actual, createRemoteJWKSet: vi.fn(() => vi.fn(async () => publicKey)) };
});

const ISSUER = "http://127.0.0.1:8080/realms/openclass-local";

type TestRequest = {
  headers: Record<string, string | undefined>;
  principal?: { subject: string; email?: string };
};

function contextFor(request: TestRequest): ExecutionContext {
  return { switchToHttp: () => ({ getRequest: () => request }) } as unknown as ExecutionContext;
}

async function signedToken(claims: { sub?: string; aud?: string; iss?: string }): Promise<string> {
  return new SignJWT({ email: "owner@acme.openclass.test" })
    .setProtectedHeader({ alg: "RS256" })
    .setIssuedAt()
    .setIssuer(claims.iss ?? ISSUER)
    .setAudience(claims.aud ?? "openclass-portal")
    .setSubject(claims.sub ?? "11111111-1111-4111-8111-111111111111")
    .setExpirationTime("5m")
    .sign(privateKey);
}

describe("KeycloakGuard", () => {
  let guard: InstanceType<typeof KeycloakGuard>;

  beforeEach(() => {
    process.env.KEYCLOAK_ISSUER_URL = ISSUER;
    process.env.KEYCLOAK_AUDIENCE = "openclass-portal";
    guard = new KeycloakGuard();
  });

  afterEach(() => {
    delete process.env.KEYCLOAK_ISSUER_URL;
    delete process.env.KEYCLOAK_AUDIENCE;
  });

  it("rejects a request without a token (401)", async () => {
    const request: TestRequest = { headers: {} };
    await expect(guard.canActivate(contextFor(request))).rejects.toThrow(
      new UnauthorizedException("Authentication required"),
    );
  });

  it("rejects a malformed token (401)", async () => {
    const request: TestRequest = { headers: { authorization: "Bearer not-a-jwt" } };
    await expect(guard.canActivate(contextFor(request))).rejects.toThrow(
      new UnauthorizedException("Invalid or expired access token"),
    );
  });

  it("rejects a token signed for another audience (401)", async () => {
    const token = await signedToken({ aud: "some-other-client" });
    const request: TestRequest = { headers: { authorization: `Bearer ${token}` } };
    await expect(guard.canActivate(contextFor(request))).rejects.toThrow(
      new UnauthorizedException("Invalid or expired access token"),
    );
  });

  it("accepts a valid token and attaches the principal", async () => {
    const subject = "22222222-2222-4222-8222-222222222222";
    const token = await signedToken({ sub: subject });
    const request: TestRequest = { headers: { authorization: `Bearer ${token}` } };
    await expect(guard.canActivate(contextFor(request))).resolves.toBe(true);
    expect(request.principal).toEqual({ subject, email: "owner@acme.openclass.test" });
  });
});
