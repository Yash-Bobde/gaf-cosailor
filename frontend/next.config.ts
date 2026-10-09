import path from 'node:path';
import type { NextConfig } from 'next';

// Pin the project root. Without this, Next/Turbopack infers the workspace root
// from the nearest lockfile ABOVE the project (e.g. a stray ~/pnpm-lock.yaml)
// and module resolution for app files can break in `next dev`.
const projectRoot = path.resolve(__dirname);

const nextConfig: NextConfig = {
  turbopack: { root: projectRoot },
  outputFileTracingRoot: projectRoot,
  // E2E tests build into their own directory so they never clobber `.next`.
  distDir: process.env.NEXT_DIST_DIR || '.next',
};

export default nextConfig;
