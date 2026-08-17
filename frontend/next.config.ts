import type { NextConfig } from "next";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: false,
  // One interview turn is a full model generation against a local Ollama,
  // which routinely outruns the default proxy timeout.
  experimental: { proxyTimeout: 300_000 },
  // Proxy API calls to FastAPI — same-origin from the browser's point of
  // view, so no CORS setup is needed.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};

export default nextConfig;
