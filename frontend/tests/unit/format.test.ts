import { describe, expect, it } from 'vitest';
import {
  callTier, leadFailureMessage, pendingLabel, runFailureMessage, safeExternalUrl, telHref,
} from '@/lib/format';

describe('callTier', () => {
  it('maps priority to the rep action', () => {
    expect(callTier({ status: 'enriched', priority_index: 8.2 }).label).toBe('Call first');
    expect(callTier({ status: 'enriched', priority_index: 6 }).label).toBe('This week');
    expect(callTier({ status: 'enriched', priority_index: 3 }).label).toBe('Nurture');
  });

  it('never shows a failed lead as "in progress"', () => {
    expect(callTier({ status: 'failed', priority_index: null }).tier).toBe('failed');
    expect(callTier({ status: 'failed', priority_index: null }).label).toBe('Needs retry');
    expect(callTier({ status: 'scraped', priority_index: null }).tier).toBe('pending');
  });
});

describe('failure messages', () => {
  it('explains a research failure without echoing internals', () => {
    const msg = leadFailureMessage('Perplexity research request failed (HTTP 401)');
    expect(msg).toContain('Web research');
    expect(msg).not.toContain('401');
    expect(msg).toContain('nothing was guessed');
  });

  it('covers timeouts and unknown errors', () => {
    expect(leadFailureMessage('Timed out before the lead finished processing')).toContain('too long');
    expect(leadFailureMessage('KeyError: x')).not.toContain('KeyError');
    expect(leadFailureMessage(null)).toContain('failed');
  });

  it('distinguishes GAF failures, restarts and unknown run errors', () => {
    expect(runFailureMessage('GAF locator page could not be loaded (TimeoutError)'))
      .toContain('reading the GAF directory');
    expect(runFailureMessage('Server restarted — pipeline was interrupted.')).toContain('server restart');
    const unknown = runFailureMessage('RuntimeError: boom at line 3');
    expect(unknown).not.toContain('RuntimeError');
  });

  it('labels pending states honestly', () => {
    expect(pendingLabel('failed')).toContain('retried');
    expect(pendingLabel('researched')).toBe('Scoring…');
  });
});

describe('links', () => {
  it('only allows http(s) URLs', () => {
    expect(safeExternalUrl('https://www.gaf.com/x')).toBe('https://www.gaf.com/x');
    expect(safeExternalUrl('javascript:alert(1)')).toBeNull();
    expect(safeExternalUrl('data:text/html,hi')).toBeNull();
    expect(safeExternalUrl('not a url')).toBeNull();
    expect(safeExternalUrl(null)).toBeNull();
  });

  it('builds dialable tel: links', () => {
    expect(telHref('(718) 555-0100')).toBe('tel:7185550100');
  });
});
