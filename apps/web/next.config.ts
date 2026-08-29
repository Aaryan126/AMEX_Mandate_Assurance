import type { NextConfig } from "next";

const staticExport = process.env.ACE_STATIC_EXPORT === "1";

const nextConfig: NextConfig = {
  output: staticExport ? "export" : "standalone",
  trailingSlash: staticExport,
  turbopack: { root: process.cwd() },
};

export default nextConfig;
