import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // /api/* is handled by src/app/api/[...path]/route.ts (cookie-aware BFF proxy).
};

export default nextConfig;
