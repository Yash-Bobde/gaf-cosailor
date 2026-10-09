/**
 * Build and serve the frontend for E2E tests, pointed at the stub backend.
 *
 * Cross-platform (no shell env syntax). Builds into .next-e2e so the regular
 * .next build is never overwritten. NEXT_PUBLIC_API_URL is inlined at build
 * time, so the build must happen with the stub URL set.
 */
import { spawnSync, spawn } from 'node:child_process';

const env = {
  ...process.env,
  NEXT_PUBLIC_API_URL: `http://127.0.0.1:${process.env.STUB_PORT || 8765}`,
  NEXT_DIST_DIR: '.next-e2e',
  NEXT_TELEMETRY_DISABLED: '1',
};
const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';
const port = process.env.E2E_APP_PORT || '3100';

const build = spawnSync(npx, ['next', 'build', '--turbopack'], { env, stdio: 'inherit', shell: process.platform === 'win32' });
if (build.status !== 0) process.exit(build.status ?? 1);

const server = spawn(npx, ['next', 'start', '-p', port, '-H', '127.0.0.1'], {
  env, stdio: 'inherit', shell: process.platform === 'win32',
});
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.kill(signal));
server.on('exit', (code) => process.exit(code ?? 0));
