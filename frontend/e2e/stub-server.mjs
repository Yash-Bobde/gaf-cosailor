/**
 * Deterministic stub of the Cosailor backend API for Playwright E2E tests.
 *
 * Serves the same routes the frontend calls (/api/leads, /api/pipeline/*),
 * for both server-side rendering and browser polling. No database, GAF or
 * Perplexity or OpenAI access. Each status poll advances a scripted run.
 *
 * Tests pick a scenario with POST /__scenario?name=<happy|cancel|run-fails|failed-lead|down>.
 */
import http from 'node:http';

const PORT = Number(process.env.STUB_PORT || 8765);
const RUN_ID = '11111111-1111-4111-8111-111111111111';
const LEAD_ID = '00000000-0000-4000-8000-000000000001';

const ENRICHED_LEAD = {
  id: LEAD_ID,
  company_name: 'Allied Brothers Construction',
  city: 'Staten Island', state: 'NY', postal_code: '10314', country_code: 'us',
  phone: '(718) 555-0100', website: null,
  gaf_profile_url: 'https://www.gaf.com/en-us/roofing-contractors/residential/usa/ny/staten-island/allied-brothers-1004211',
  segment: 'residential', certifications: ['GAF Master Elite'], rating: 4.9, review_count: 120,
  research_summary: 'Allied Brothers was founded in 2004. Owner Maria Lopez oversees all bids.',
  research_sources: ['https://alliedbrothers.example/about', 'https://www.bbb.org/allied-brothers'],
  decision_makers: [
    { name: 'Maria Lopez', title: 'Owner', role: 'decision_maker',
      source_url: 'https://www.bbb.org/allied-brothers', evidence: 'Owner Maria Lopez oversees all bids.' },
    { name: 'Dev Patel', title: null, role: 'contact', source_url: null,
      evidence: 'Dev Patel answered our scheduling questions.' },
  ],
  lead_score: 9, score_rationale: 'Master Elite with 120 strong reviews.',
  convertibility_score: 6, convertibility_rationale: 'Mentions Owens Corning on some jobs.',
  distance_miles: 12.4, distance_band: 'near', priority_index: 7.5,
  ai_summary: 'A top-tier residential installer on Staten Island that still quotes a competitor brand.',
  talking_points: ['Master Elite status', 'Owens Corning gap', 'Staten Island volume'],
  recommended_approach: 'Ask for Maria Lopez and lead with warranty tiers.',
  status: 'enriched', error_message: null,
  enriched_at: '2026-10-09T10:00:30Z', created_at: '2026-10-09T10:00:05Z',
};

let state;

const FAILED_LEAD = {
  ...ENRICHED_LEAD, id: '00000000-0000-4000-8000-000000000002', company_name: 'Harbor Roofing LLC',
  status: 'failed', error_message: 'Perplexity research request failed (HTTP 401)',
  research_summary: null, research_sources: [], decision_makers: [], lead_score: null,
  convertibility_score: null, priority_index: null, ai_summary: null, talking_points: [],
  recommended_approach: null, score_rationale: null, convertibility_rationale: null, enriched_at: null,
};

function reset(scenario = 'happy') {
  state = { scenario, run: null, polls: 0, leads: scenario === 'failed-lead' ? [ENRICHED_LEAD, FAILED_LEAD] : [] };
}
reset();

function runRow(patch) {
  return {
    run_id: RUN_ID, status: 'running', leads_scraped: 0, leads_enriched: 0, leads_failed: 0,
    cancel_requested: false, started_at: '2026-10-09T10:00:00Z', finished_at: null,
    error_message: null, postal_code: '10013', country_code: 'us', distance: 25,
    segment: 'residential', ...state.run, ...patch,
  };
}

/** Advance the scripted run by one poll. */
function advance() {
  state.polls += 1;
  const { scenario, polls } = state;
  if (scenario === 'happy') {
    if (polls === 1) {
      state.leads = [{ ...ENRICHED_LEAD, status: 'scraped', lead_score: null, convertibility_score: null,
        priority_index: null, ai_summary: null, decision_makers: [], talking_points: [] }];
      state.run = runRow({ leads_scraped: 1 });
    } else {
      state.leads = [ENRICHED_LEAD];
      state.run = runRow({ leads_scraped: 1, leads_enriched: 1,
        ...(polls >= 3 ? { status: 'completed', finished_at: '2026-10-09T10:00:40Z' } : {}) });
    }
  } else if (scenario === 'cancel') {
    state.run = state.run.cancel_requested
      ? runRow({ status: 'cancelled', leads_scraped: 5, leads_enriched: 1, finished_at: '2026-10-09T10:01:00Z' })
      : runRow({ leads_scraped: 5, leads_enriched: 1 });
  } else if (scenario === 'run-fails') {
    state.run = runRow({ status: 'failed', finished_at: '2026-10-09T10:00:50Z',
      error_message: 'GAF locator page could not be loaded (TimeoutError)' });
  }
  return state.run;
}

function send(res, status, body) {
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  });
  res.end(body === undefined ? '' : JSON.stringify(body));
}

function route(req, res, url) {
  const path = url.pathname;
  if (req.method === 'OPTIONS') return send(res, 204);
  if (path === '/__scenario') { reset(url.searchParams.get('name') || 'happy'); return send(res, 200, state); }
  if (path === '/health') return send(res, 200, { status: 'ok' });
  if (state.scenario === 'down') return send(res, 500, { detail: 'down' });
  if (path === '/api/leads/' || path === '/api/leads') {
    return send(res, 200, { leads: state.leads, total: state.leads.length, page: 1, limit: 20 });
  }
  const lead = path.match(/^\/api\/leads\/([^/]+)$/);
  if (lead) {
    const found = state.leads.find((l) => l.id === lead[1]);
    return found ? send(res, 200, found) : send(res, 404, { detail: 'Lead not found' });
  }
  if (path === '/api/pipeline/run' && req.method === 'POST') {
    if (state.run?.status === 'running') {
      return send(res, 409, { detail: { message: 'busy', run_id: RUN_ID } });
    }
    state.run = runRow({});
    return send(res, 202, { run_id: RUN_ID, status: 'running', message: 'started' });
  }
  if (path === `/api/pipeline/${RUN_ID}/cancel` && req.method === 'POST') {
    state.run = runRow({ cancel_requested: true });
    return send(res, 202, { run_id: RUN_ID, status: 'running', cancel_requested: true });
  }
  if (path === '/api/pipeline/latest') return state.run ? send(res, 200, state.run) : send(res, 204);
  if (path === `/api/pipeline/status/${RUN_ID}`) return send(res, 200, advance());
  return send(res, 404, { detail: 'not found' });
}

http.createServer((req, res) => {
  try {
    route(req, res, new URL(req.url, `http://127.0.0.1:${PORT}`));
  } catch (err) {
    send(res, 500, { detail: String(err) });
  }
}).listen(PORT, '127.0.0.1', () => console.log(`stub backend on http://127.0.0.1:${PORT}`));
