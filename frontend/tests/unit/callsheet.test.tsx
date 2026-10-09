import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CallSheet, type SheetQuery } from '@/components/CallSheet';
import { makeLead } from '../fixtures';

const query: SheetQuery = { page: 1, limit: 20, scoreTier: 'all', sortBy: 'score_desc', segment: 'all' };

describe('CallSheet', () => {
  it('renders ranked rows with the action tier, scores and a call button', () => {
    render(<CallSheet leads={[makeLead()]} total={1} query={query} />);
    const row = screen.getByRole('listitem');
    expect(within(row).getByText('Call first')).toBeInTheDocument();
    expect(within(row).getByRole('img', { name: 'Fit 9 of 10' })).toBeInTheDocument();
    expect(within(row).getByRole('img', { name: 'Opportunity 6 of 10' })).toBeInTheDocument();
    expect(within(row).getByRole('link', { name: 'Call Allied Brothers Construction' }))
      .toHaveAttribute('href', 'tel:7185550100');
    expect(within(row).getByRole('link', { name: 'Allied Brothers Construction' }))
      .toHaveAttribute('href', `/leads/${makeLead().id}`);
  });

  it('shows failed leads as "Needs retry" without raw error text', () => {
    const failed = makeLead({ status: 'failed', priority_index: null, lead_score: null,
      convertibility_score: null, ai_summary: null,
      error_message: 'Perplexity research request failed (HTTP 401)' });
    render(<CallSheet leads={[failed]} total={1} query={query} />);
    expect(screen.getByText('Needs retry')).toBeInTheDocument();
    expect(screen.getByText(/retried on the next run/)).toBeInTheDocument();
    expect(screen.queryByText(/HTTP 401/)).toBeNull();
    expect(screen.queryByRole('img', { name: /Fit/ })).toBeNull();
  });

  it('builds shareable filter, segment and sort links', () => {
    render(<CallSheet leads={[makeLead()]} total={1} query={{ ...query, segment: 'residential' }} />);
    expect(screen.getByRole('link', { name: 'Fit 8–10' })).toHaveAttribute('href', '/?score_tier=high&segment=residential');
    expect(screen.getByRole('link', { name: 'Commercial' })).toHaveAttribute('href', '/?segment=commercial');
    expect(screen.getByRole('link', { name: 'Residential' })).toHaveAttribute('aria-current', 'true');
    expect(screen.getByRole('link', { name: 'A–Z' })).toHaveAttribute('href', '/?sort_by=name_asc&segment=residential');
  });

  it('paginates with accurate ranges', () => {
    const leads = Array.from({ length: 20 }, (_, i) => makeLead({ id: `id-${i}`, company_name: `Roofer ${i}` }));
    render(<CallSheet leads={leads} total={45} query={{ ...query, page: 2 }} />);
    expect(screen.getByText('21–40 of 45')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /next/i })).toHaveAttribute('href', '/?page=3');
    expect(screen.getByRole('link', { name: /prev/i })).toHaveAttribute('href', '/');
  });

  it('offers a way back when a filter matches nothing', () => {
    render(<CallSheet leads={[]} total={0} query={{ ...query, scoreTier: 'low' }} />);
    expect(screen.getByText('No contractors match this filter.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Show all leads' })).toHaveAttribute('href', '/');
  });
});
