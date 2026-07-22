/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  experimental: {
    // We talk to LangGraph via server-side proxy in /api/proxy/* — keeps
    // user-facing origin clean and lets us inject secrets later.
    serverActions: { bodySizeLimit: "2mb" },
  },
  async rewrites() {
    const upstream = process.env.LANGGRAPH_URL || "http://langgraph-app:8080";
    return [
      // Proxy backend API under /api/v1/* so the browser only ever talks to
      // the same origin as the UI (no CORS concerns in production).
      { source: "/api/v1/:path*", destination: `${upstream}/api/v1/:path*` },
    ];
  },
};

export default nextConfig;
