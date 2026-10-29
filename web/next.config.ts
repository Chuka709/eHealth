import path from "node:path";
import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  // No cacheComponents / partial prerendering: every page here (admin panel, share viewer)
  // is per-request, and a prerendered shell's scripts cannot carry the per-request CSP nonce
  // (docs: nonce CSP is incompatible with PPR).
  // Self-contained server for the Docker image; trace files from the monorepo root.
  output: "standalone",
  outputFileTracingRoot: path.join(import.meta.dirname, ".."),
  transpilePackages: ["@labtrack/shared"],
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  turbopack: {
    root: path.join(import.meta.dirname, ".."),
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default createNextIntlPlugin("./src/i18n/request.ts")(nextConfig);
