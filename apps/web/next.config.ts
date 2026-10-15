import type { NextConfig } from "next";
import path from "node:path";
const server = process.env.OPENCLASS_SERVER_URL ?? "http://127.0.0.1:7331";
const config: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
  transpilePackages: ["@openclass/sdk"],
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${server}/api/v1/:path*` },
      { source: "/health/:path*", destination: `${server}/health/:path*` },
    ];
  },
};
export default config;
