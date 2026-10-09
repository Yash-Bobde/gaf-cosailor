import type { Lead, PipelineStatusResponse } from '@/lib/types';

export function makeLead(overrides: Partial<Lead> = {}): Lead {
  return {
    id: '00000000-0000-4000-8000-000000000001',
    company_name: 'Allied Brothers Construction',
    city: 'Staten Island',
    state: 'NY',
    postal_code: '10314',
    country_code: 'us',
    phone: '(718) 555-0100',
    website: null,
    gaf_profile_url: 'https://www.gaf.com/en-us/roofing-contractors/residential/usa/ny/staten-island/allied-brothers-1004211',
    segment: 'residential',
    certifications: ['GAF Master Elite'],
    rating: 4.9,
    review_count: 120,
    research_summary: 'Owner Maria Lopez founded Allied Brothers in 2004.',
    research_sources: ['https://alliedbrothers.example/about'],
    decision_makers: [],
    lead_score: 9,
    score_rationale: 'Master Elite with strong reviews.',
    convertibility_score: 6,
    convertibility_rationale: 'Competitor brands mentioned.',
    distance_miles: 12.4,
    distance_band: 'near',
    priority_index: 7.5,
    ai_summary: 'A top-tier residential installer on Staten Island.',
    talking_points: ['Point one', 'Point two', 'Point three'],
    recommended_approach: 'Ask for the owner.',
    status: 'enriched',
    error_message: null,
    enriched_at: '2026-09-25T12:00:00Z',
    created_at: '2026-09-25T11:00:00Z',
    ...overrides,
  };
}

export function makeRun(overrides: Partial<PipelineStatusResponse> = {}): PipelineStatusResponse {
  return {
    run_id: '11111111-1111-4111-8111-111111111111',
    status: 'running',
    leads_scraped: 0,
    leads_enriched: 0,
    leads_failed: 0,
    cancel_requested: false,
    started_at: '2026-10-09T10:00:00Z',
    finished_at: null,
    error_message: null,
    postal_code: '10013',
    country_code: 'us',
    distance: 25,
    segment: 'residential',
    ...overrides,
  };
}
