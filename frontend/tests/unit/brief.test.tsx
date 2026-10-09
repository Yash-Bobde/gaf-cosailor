import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DecisionMakers, Sources } from '@/components/brief/BriefSections';
import { ScoreCard } from '@/components/brief/ScoreCard';
import { makeLead } from '../fixtures';

describe('DecisionMakers', () => {
  it('labels decision-makers vs contacts and shows the supporting sentence', () => {
    render(<DecisionMakers people={[
      { name: 'Maria Lopez', title: 'Owner', role: 'decision_maker',
        source_url: 'https://bbb.org/acme', evidence: 'Owner Maria Lopez oversees all bids.' },
      { name: 'Dev Patel', title: null, role: 'contact', source_url: null, evidence: null },
    ]} />);

    const [maria, dev] = screen.getAllByRole('listitem');
    expect(within(maria).getByText('Decision-maker')).toBeInTheDocument();
    expect(within(maria).getByText(/Owner Maria Lopez oversees all bids/)).toBeInTheDocument();
    expect(within(maria).getByRole('link', { name: /bbb\.org/ })).toHaveAttribute('rel', 'noopener noreferrer');
    expect(within(dev).getByText('Contact')).toBeInTheDocument();
    expect(within(dev).getByText('Title unknown')).toBeInTheDocument();
    expect(within(dev).queryByRole('link')).toBeNull();
  });

  it('treats legacy rows without a role as contacts', () => {
    render(<DecisionMakers people={[{ name: 'Old Record', title: 'Owner', source_url: null }]} />);
    expect(screen.getByText('Contact')).toBeInTheDocument();
    expect(screen.queryByText('Decision-maker')).toBeNull();
  });

  it('says so when no one could be confirmed, instead of inventing a contact', () => {
    render(<DecisionMakers people={[]} />);
    expect(screen.getByText(/No named people could be confirmed/)).toBeInTheDocument();
  });

  it('never renders a javascript: source link', () => {
    render(<DecisionMakers people={[
      { name: 'Eve Evans', title: null, role: 'contact', source_url: 'javascript:alert(1)' },
    ]} />);
    expect(screen.queryByRole('link')).toBeNull();
  });
});

describe('Sources', () => {
  it('lists citations as safe external links and drops unsafe ones', () => {
    render(<Sources urls={['https://www.bbb.org/acme', 'javascript:alert(1)']} />);
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('target', '_blank');
    expect(links[0]).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('shows an honest empty state', () => {
    render(<Sources urls={[]} />);
    expect(screen.getByText('No citations were returned for this lead.')).toBeInTheDocument();
  });
});

describe('ScoreCard', () => {
  it('offers a safe "View GAF profile" action', () => {
    render(<ScoreCard lead={makeLead()} />);
    const profile = screen.getByRole('link', { name: /view gaf profile/i });
    expect(profile).toHaveAttribute('href', makeLead().gaf_profile_url);
    expect(profile).toHaveAttribute('target', '_blank');
    expect(profile).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('hides the GAF action when the URL is missing or unsafe', () => {
    render(<ScoreCard lead={makeLead({ gaf_profile_url: 'javascript:alert(1)' })} />);
    expect(screen.queryByRole('link', { name: /view gaf profile/i })).toBeNull();
  });

  it('keeps click-to-call and calls the second score "Opportunity"', () => {
    render(<ScoreCard lead={makeLead()} />);
    expect(screen.getByRole('link', { name: /call \(718\) 555-0100/i })).toHaveAttribute('href', 'tel:7185550100');
    expect(screen.getByRole('img', { name: 'Opportunity 6 of 10' })).toBeInTheDocument();
    expect(screen.queryByText('Convert')).toBeNull();
  });

  it('explains the rank arithmetic without claiming a win probability', () => {
    render(<ScoreCard lead={makeLead({ lead_score: 9, convertibility_score: 6, priority_index: 7.5 })} />);
    expect(screen.getByText(/\(Fit 9 \+ Opportunity 6\) ÷ 2 × 1\.00/)).toBeInTheDocument();
    expect(screen.getByText(/not predicted win rates/)).toBeInTheDocument();
  });
});
