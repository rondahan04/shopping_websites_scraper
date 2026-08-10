import type { NextConfig } from "next";

const apiOrigin = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

/**
 * In demo mode there is no backend to proxy to, so the rewrites are dropped
 * entirely. Pointing /api/* at an unreachable origin would turn every request
 * into a hung fetch rather than a clean client-side answer.
 */
const isDemo = process.env.NEXT_PUBLIC_DEMO === "1";

const nextConfig: NextConfig = {
  async rewrites() {
    if (isDemo) return [];
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${apiOrigin}/health`,
      },
    ];
  },
};

export default nextConfig;
