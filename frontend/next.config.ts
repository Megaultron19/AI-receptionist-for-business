import type { NextConfig } from "next";

const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
const dev = process.env.NODE_ENV === "development";

const config: NextConfig = dev
  ? {
      async rewrites() {
        return ["api", "q", "webhooks", "voice"].map((p) => ({ source: `/${p}/:path*`, destination: `${backend}/${p}/:path*` }));
      },
    }
  : { output: "export", trailingSlash: true, images: { unoptimized: true } };

export default config;
