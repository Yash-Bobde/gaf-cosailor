import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { makeRun } from '../fixtures';

const refresh = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh }) }));

const api = vi.hoisted(() => ({
  startPipeline: vi.fn(),
  cancelPipeline: vi.fn(),
  getPipelineStatus: vi.fn(),
  getLatestPipelineRun: vi.fn(),
}));
vi.mock('@/lib/api', () => api);

import { RunPanel } from '@/components/RunPanel';

async function renderPanel() {
  render(<RunPanel />);
  await act(async () => {});   // let the "restore latest run" effect settle
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  api.getLatestPipelineRun.mockResolvedValue(null);
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('RunPanel form', () => {
  it('defaults to the case-study search: residential, 10013, 25 mi', async () => {
    await renderPanel();
    expect(screen.getByLabelText('ZIP code')).toHaveValue('10013');
    expect(screen.getByRole('button', { name: '25 mi' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Residential' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('rejects an invalid ZIP and disables the run button', async () => {
    await renderPanel();
    fireEvent.change(screen.getByLabelText('ZIP code'), { target: { value: '12a' } });
    expect(screen.getByText('Enter a 5-digit US ZIP')).toBeInTheDocument();
    expect(screen.getByLabelText('ZIP code')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('button', { name: /build call list/i })).toBeDisabled();
  });

  it('starts a run with the chosen parameters and shows progress', async () => {
    api.startPipeline.mockResolvedValue({ run_id: 'r1', attached: false });
    await renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '50 mi' }));
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /build call list/i })); });

    expect(api.startPipeline).toHaveBeenCalledWith(
      { postal_code: '10013', country_code: 'us', distance: 50, segment: 'residential', limit: 10 });
    expect(screen.getByText('Finding contractors on GAF…')).toBeInTheDocument();
  });

  it('attaches to an already-running run (409) and shows its live counts', async () => {
    api.startPipeline.mockResolvedValue({ run_id: 'r-active', attached: true });
    api.getPipelineStatus.mockResolvedValue(makeRun({ run_id: 'r-active', leads_scraped: 8, leads_enriched: 3 }));
    await renderPanel();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /build call list/i })); });

    expect(api.getPipelineStatus).toHaveBeenCalledWith('r-active');
    expect(screen.getByText('Researching and scoring each lead…')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '38');
  });

  it('explains a backend that cannot be reached when starting', async () => {
    api.startPipeline.mockRejectedValue(new TypeError('fetch failed'));
    await renderPanel();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /build call list/i })); });
    expect(screen.getByRole('alert')).toHaveTextContent('port 8000');
  });
});

describe('RunPanel while running', () => {
  it('polls, refreshes the call sheet and shows the completed outcome', async () => {
    api.getLatestPipelineRun.mockResolvedValue(makeRun({ leads_scraped: 2 }));
    api.getPipelineStatus.mockResolvedValue(
      makeRun({ status: 'completed', leads_scraped: 2, leads_enriched: 2, finished_at: '2026-09-26T10:01:00Z' }));
    await renderPanel();

    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Last run scored 2 of 2 contractors.')).toBeInTheDocument();
    // the date of that run sits next to the outcome, so reps know how fresh the sheet is
    const when = screen.getByText('Sep 26, 2026');
    expect(when).toHaveAttribute('dateTime', '2026-09-26T10:01:00Z');
    expect(when.parentElement).toHaveTextContent('Last Build Call List Ran: Sep 26, 2026');

    // a final refresh after the terminal state guarantees the list shows finished leads
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it('requests cancellation and shows the draining state', async () => {
    api.getLatestPipelineRun.mockResolvedValue(makeRun({ leads_scraped: 5, leads_enriched: 1 }));
    api.cancelPipeline.mockResolvedValue(undefined);
    await renderPanel();

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /cancel run/i })); });

    expect(api.cancelPipeline).toHaveBeenCalledWith(makeRun().run_id);
    expect(screen.getByText('Stopping after the leads in progress…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel run/i })).toBeDisabled();
  });

  it('warns after repeated failed polls instead of failing silently', async () => {
    api.getLatestPipelineRun.mockResolvedValue(makeRun({ leads_scraped: 5 }));
    api.getPipelineStatus.mockRejectedValue(new TypeError('fetch failed'));
    await renderPanel();

    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(screen.queryByRole('alert')).toBeNull();
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(screen.getByRole('alert')).toHaveTextContent('Lost contact with the backend');
  });

  it('describes a failed GAF scrape in plain language', async () => {
    api.getLatestPipelineRun.mockResolvedValue(makeRun({
      status: 'failed', error_message: 'GAF locator page could not be loaded (TimeoutError)',
    }));
    await renderPanel();
    expect(screen.getByText(/reading the GAF directory/)).toBeInTheDocument();
  });

  it('reports a genuine zero-result run as such', async () => {
    api.getLatestPipelineRun.mockResolvedValue(makeRun({ status: 'completed', leads_scraped: 0 }));
    await renderPanel();
    expect(screen.getByText(/GAF lists no contractors/)).toBeInTheDocument();
  });
});
