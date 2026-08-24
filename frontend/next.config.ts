import type { NextConfig } from "next";

// Baked in at build time: Next serializes rewrites() into the build manifest,
// so this must already be correct when `next build` runs. Compose passes it as
// the BACKEND_URL build arg; the fallback is for `npm run dev` on the host.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: false,
  // Model-backed requests can take up to five minutes. Keep enough headroom
  // for proxying and server-side processing around the model response.
  experimental: { proxyTimeout: 600_000 },
  // Proxy API calls to FastAPI — same-origin from the browser's point of
  // view, so no CORS setup is needed.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};

export default nextConfig;
