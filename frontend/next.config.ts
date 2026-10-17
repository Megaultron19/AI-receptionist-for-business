import type { NextConfig } from "next";

const dev = process.env.NODE_ENV === "development";

const config: NextConfig = dev
  ? { async rewrites() { return [{ source: "/api/:path*", destination: "http://localhost:8000/api/:path*" }]; } }
  : { output: "export", trailingSlash: true };

export default config;
