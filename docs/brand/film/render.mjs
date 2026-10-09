// Encode brand-film.html to MP4, frame by frame (deterministic, no dropped frames).
//
//   FFMPEG=/path/to/ffmpeg node docs/brand/film/render.mjs [out.mp4] [--fps 30]
//   node docs/brand/film/render.mjs --stills 4,9,15 --stills-dir <dir>   # PNG stills at those seconds
//
// Uses the Playwright install in frontend/node_modules. Any ffmpeg with libx264 works
// (e.g. `pip install imageio-ffmpeg`).
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(resolve(here, '../../../frontend/package.json'));
const { chromium } = require('@playwright/test');

const args = process.argv.slice(2);
const flag = (name, dflt) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : dflt; };
const fps = Number(flag('--fps', 30));
const stills = flag('--stills', null);
const out = resolve(args.find((a, i) => !a.startsWith('--') && !args[i - 1]?.startsWith('--')) ?? resolve(here, '../cosailor-brand-film.mp4'));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
await page.goto(pathToFileURL(resolve(here, 'brand-film.html')).href + '?capture');
await page.evaluate(() => document.fonts.ready);
const duration = await page.evaluate(() => window.DURATION);
const total = Math.round(duration * fps);
const shot = (i) => page.evaluate((t) => window.render(t), i / fps).then(() => page.screenshot({ type: 'png' }));

if (stills) {
  const dir = resolve(flag('--stills-dir', resolve(here, 'stills')));
  mkdirSync(dir, { recursive: true });
  for (const sec of stills.split(',').map(Number)) writeFileSync(resolve(dir, `t${String(sec).padStart(5, '0')}.png`), await shot(Math.round(sec * fps)));
  await browser.close();
  process.exit(0);
}

// Soundtrack: `python docs/brand/film/score.py` writes score.wav next to this file.
const score = resolve(here, 'score.wav');
const audio = existsSync(score) ? ['-i', score, '-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '192k', '-shortest'] : [];
if (!audio.length) console.log('no score.wav found; encoding without music (run score.py first)');

const ff = spawn(process.env.FFMPEG ?? 'ffmpeg', [
  '-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'png', '-i', '-', ...audio,
  '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out,
], { stdio: ['pipe', 'inherit', 'inherit'] });

for (let i = 0; i < total; i++) {
  const buf = await shot(i);
  if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
  if (i % (fps * 5) === 0) console.log(`frame ${i}/${total}`);
}
ff.stdin.end();
const code = await new Promise((r) => ff.on('close', r));
await browser.close();
console.log(code === 0 ? `wrote ${out}` : `ffmpeg exited ${code}`);
process.exit(code);
