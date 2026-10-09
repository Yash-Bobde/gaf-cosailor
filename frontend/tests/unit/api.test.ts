import { afterEach, describe, expect, it, vi } from 'vitest';
import { cancelPipeline, getLatestPipelineRun, getLead, startPipeline } from '@/lib/api';

const params = { postal_code: '10013', country_code: 'us', distance: 25, segment: 'residential', limit: 10 } as const;

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));
  vi.stubGlobal('fetch', fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('startPipeline', () => {
  it('returns the new run id on 202', async () => {
    mockFetch(202, { run_id: 'r-new', status: 'running', message: 'ok' });
    await expect(startPipeline(params)).resolves.toEqual({ run_id: 'r-new', attached: false });
  });

  it('attaches to the active run on 409 instead of failing', async () => {
    mockFetch(409, { detail: { message: 'busy', run_id: 'r-active' } });
    await expect(startPipeline(params)).resolves.toEqual({ run_id: 'r-active', attached: true });
  });

  it('throws on other errors', async () => {
    mockFetch(500, { detail: 'boom' });
    await expect(startPipeline(params)).rejects.toThrow('500');
  });
});

describe('cancelPipeline', () => {
  it('treats 409 (already finished) as done', async () => {
    mockFetch(409, { detail: 'Run is completed, not running' });
    await expect(cancelPipeline('r1')).resolves.toBeUndefined();
  });

  it('throws when the backend errors', async () => {
    mockFetch(500, {});
    await expect(cancelPipeline('r1')).rejects.toThrow();
  });
});

describe('getLead', () => {
  it('returns null for an unknown lead', async () => {
    mockFetch(404, { detail: 'Lead not found' });
    await expect(getLead('missing')).resolves.toBeNull();
  });
});

describe('getLatestPipelineRun', () => {
  it('returns null when no run exists yet (204)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(getLatestPipelineRun()).resolves.toBeNull();
  });
});
