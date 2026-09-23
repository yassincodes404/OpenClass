import type { NextConfig } from "next";
const server = process.env.OPENCLASS_SERVER_URL ?? "http://127.0.0.1:7331";
const config: NextConfig = {
  transpilePackages: ["@openclass/sdk"],
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${server}/api/v1/:path*` },
      { source: "/health/:path*", destination: `${server}/health/:path*` },
    ];
  },
};
export default config;
