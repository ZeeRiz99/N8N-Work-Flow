import type { NextConfig } from "next";

// The browser talks to ONE origin (this app). /api/* is forwarded to the FastAPI backend, so the
// backend's httpOnly session cookies are first-party here. 127.0.0.1, not localhost: on Windows,
// localhost tries IPv6 first and the backend listens on IPv4.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
