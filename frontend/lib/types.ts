/**
 * Shared TypeScript types for the Cosailor Insights frontend.
 *
 * These interfaces mirror the backend Pydantic models so the compiler can
 * catch shape mismatches between API responses and UI components at build time.
 */

export type Segment = 'residential' | 'commercial';
export type LeadStatus = 'scraped' | 'researched' | 'enriched' | 'failed';
export type RunStatus = 'running' | 'completed' | 'failed' | 'cancelled';
export type ScoreTier = 'all' | 'high' | 'medium' | 'low';
export type SortOption = 'score_desc' | 'name_asc' | 'recently_enriched';

/**
 * 'decision_maker' = the research supports a leadership/purchasing title for this person.
 * 'contact'        = named in the research, but authority is not supported (or unknown).
 */
export type ContactRole = 'decision_maker' | 'contact';

/** A person named (full name) in the public web research for this contractor. */
export interface DecisionMaker {
  name: string;
  /** Only present when the research supports it; null = unknown. */
  title: string | null;
  /** A citation URL Perplexity returned from its web search, never a model-invented link. */
  source_url: string | null;
  /** Older rows (before roles existed) arrive as 'contact' from the API. */
  role?: ContactRole;
  /** The research sentence that names this person. */
  evidence?: string | null;
}

/** A single contractor lead row as returned by GET /api/leads and GET /api/leads/:id. */
export interface Lead {
  id: string;
  company_name: string;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country_code: string;
  phone: string | null;
  website: string | null;
  /** GAF's own profile page for this contractor (from the directory's clickUri). */
  gaf_profile_url: string | null;
  segment?: Segment | null;
  certifications: string[];
  rating: number | null;
  review_count: number | null;
  /** Raw web-research text (with inline citation links) stored after the research stage. */
  research_summary: string | null;
  /** Citation URLs Perplexity returned from its web search. */
  research_sources?: string[];
  decision_makers?: DecisionMaker[];
  /** Fit score on a 1–10 scale; null until the lead is enriched. */
  lead_score: number | null;
  score_rationale: string | null;
  /**
   * Rules-based OPPORTUNITY score (1–10): portfolio-gap, growth and certification signals
   * found in the research. Not a validated conversion probability. null until enriched.
   */
  convertibility_score: number | null;
  convertibility_rationale: string | null;
  distance_miles: number | null;
  distance_band: 'near' | 'mid' | 'far' | null;
  /** Composite rank: (lead_score + convertibility_score) / 2 × distance modifier (1.00 / 0.95 / 0.90). */
  priority_index: number | null;
  ai_summary: string | null;
  talking_points: string[];
  recommended_approach: string | null;
  status: LeadStatus;
  error_message: string | null;
  enriched_at: string | null;
  created_at: string;
}

/** Paginated response from GET /api/leads. */
export interface PaginatedLeadsResponse {
  leads: Lead[];
  total: number;
  page: number;
  limit: number;
}

/** Parameters for POST /api/pipeline/run. limit=null means "all contractors found". */
export interface PipelineRunParams {
  postal_code: string;
  country_code: 'us';
  distance: 25 | 50 | 100;
  segment: Segment;
  limit: number | null;
}

/** Result of starting a run. attached=true when a run was already active (HTTP 409). */
export interface PipelineStartResult {
  run_id: string;
  attached: boolean;
}

/** Current state of a pipeline run, returned by /status/:run_id and /latest. */
export interface PipelineStatusResponse {
  run_id: string;
  status: RunStatus;
  leads_scraped: number;
  leads_enriched: number;
  leads_failed?: number;
  cancel_requested?: boolean;
  started_at: string;
  finished_at: string | null;
  error_message: string | null;
  postal_code: string;
  country_code: string;
  distance: number;
  segment?: Segment;
}
