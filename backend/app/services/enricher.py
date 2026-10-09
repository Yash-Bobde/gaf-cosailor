"""OpenAI lead enrichment service.

LeadEnricher orchestrates the following for each contractor:
  1. Compute deterministic scoring baselines via ScoringService.
  2. Call the configured OpenAI model with a structured prompt containing GAF
     data, web research, and the pre-computed baselines.
  3. Parse and clamp the returned JSON to within ±1 of each Python baseline.
  4. Ground people (services/grounding.py): keep only full names that appear in
     the web research, keep a title only where the research supports it, label
     each person 'decision_maker' or 'contact', and keep only real citation URLs.
  5. Assemble and return a LeadInsight ready for database persistence.

The scoring baselines act as an anchor: the model may adjust each score by at
most ±1 based on research context, keeping outputs deterministic and auditable
regardless of LLM temperature drift. The same philosophy applies to people:
the model proposes, deterministic code verifies.
"""
import asyncio
import json
import logging
import re
from openai import OpenAI
from app.models.lead import ContractorRecord, LeadInsight
from app.services.grounding import ground_decision_makers
from app.services.scorer import ScoringService, compute_priority_index

__all__ = ["LeadEnricher", "ground_decision_makers"]

logger = logging.getLogger(__name__)

# System prompt instructs the model to return a single JSON object with no
# markdown wrapping. Strict format required because _parse() only does one
# level of fence-stripping before raising.
_SYSTEM = """You are a sales intelligence analyst for a roofing materials distributor.
Score and analyze roofing contractor leads for sales rep prioritization.

IMPORTANT: Respond with a single valid JSON object — NO markdown fences, NO preamble.

Required keys:
  lead_score               (integer — must equal lead baseline ± 1 at most)
  score_rationale          (string, 1 sentence)
  convertibility_score     (integer — must equal convertibility baseline ± 1 at most)
  convertibility_rationale (string, 1 sentence)
  ai_summary               (string, 2-3 sentences)
  talking_points           (array of exactly 3 strings)
  recommended_approach     (string, 1-2 sentences)
  decision_makers          (array of {"name", "title", "source_url"} — ONLY people named
                            with their FULL name in the WEB RESEARCH section, name and title
                            copied exactly as written there; title null if the research
                            gives none; [] if none)"""

def _fmt(detected: bool) -> str:
    """Convert a boolean signal flag to a human-readable label for the LLM prompt."""
    return "DETECTED" if detected else "NOT FOUND"


def _prompt(c: ContractorRecord, research: dict, lead_comps, conv_comps) -> str:
    """Build the user turn sent to the model with contractor data, research, and baselines.

    Baselines are embedded in the prompt so the model can see the Python-computed
    anchor values before producing its response, enabling the ±1 adjustment rule.
    """
    certs = ", ".join(c.certifications) if c.certifications else "none"
    lead_int = round(lead_comps.baseline)
    conv_int  = round(conv_comps.baseline)

    return f"""Analyze this lead.

=== GAF DATA ===
Company: {c.company_name}
Location: {c.city or ''}, {c.state or ''} {c.postal_code or ''}
Phone: {c.phone or 'N/A'}
Website: {c.website or 'N/A'}
GAF Certifications: {certs}
Rating: {c.rating or 'N/A'} ({c.review_count or 0} reviews)

=== WEB RESEARCH ===
{research.get('summary') or 'No research available.'}

=== SCORING BASELINES ===
Lead score baseline: {lead_comps.baseline} → rounded to {lead_int}
  - Certification:  {lead_comps.cert_points:.1f} pts (weight 40%)
  - Size/Revenue:   {lead_comps.size_points:.1f} pts (weight 25%) → unknown, use research context
  - Star Rating:    {lead_comps.rating_points:.1f} pts (weight 25%)
  - Review Count:   {lead_comps.review_points:.1f} pts (weight 10%)

Convertibility baseline: {conv_comps.baseline} → rounded to {conv_int}
  - Portfolio gap:      {_fmt(conv_comps.portfolio_gap_detected)}   (40%)
  - Growth signals:     {_fmt(conv_comps.growth_signal_detected)}   (35%)
  - Cert momentum:      {_fmt(conv_comps.cert_momentum_detected)}   (25%)

RULES:
- You may adjust lead_score by ±1 from its baseline ({lead_int}) based on research context.
- You may adjust convertibility_score by ±1 from its baseline ({conv_int}) based on research context.
- Do not exceed these bounds under any circumstances.
- Return both scores as integers.

Return JSON with the exact keys from your instructions.
Talking points must reference this specific contractor's certifications, location, or research findings.
For decision_makers, copy names exactly as they appear in the WEB RESEARCH; return [] if none are named."""


def _clamp(value, baseline: float) -> int:
    """Clamp a model-proposed score to baseline ±1 and to the 1–10 range."""
    anchor = round(baseline)
    try:
        proposed = int(value)
    except (TypeError, ValueError):
        proposed = anchor
    return max(max(1, anchor - 1), min(min(10, anchor + 1), proposed))


class LeadEnricher:
    """Enriches a contractor record with OpenAI scoring and sales intelligence."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", max_retries: int = 2):
        self._client = OpenAI(api_key=api_key, max_retries=max_retries)
        self._model = model
        self._scorer = ScoringService()

    def enrich(
        self,
        contractor: ContractorRecord,
        research: dict,
        search_postal_code: str = "",
    ) -> LeadInsight:
        """Compute baselines, ask the model, then clamp scores and ground people."""
        lead_comps = self._scorer.compute_lead_baseline(contractor)
        conv_comps = self._scorer.compute_convertibility_baseline(research.get("summary"))
        distance = self._scorer.compute_distance(contractor.postal_code, search_postal_code)

        data = self._ask_model(_prompt(contractor, research, lead_comps, conv_comps))
        lead_score = _clamp(data.get("lead_score"), lead_comps.baseline)
        conv_score = _clamp(data.get("convertibility_score"), conv_comps.baseline)

        return LeadInsight(
            lead_score=lead_score,
            score_rationale=data.get("score_rationale")
            or "Lead score based on certifications, rating, and review volume.",
            convertibility_score=conv_score,
            convertibility_rationale=data.get("convertibility_rationale")
            or "Opportunity score based on detected portfolio-gap, growth and certification signals.",
            ai_summary=data.get("ai_summary") or "",
            talking_points=(data.get("talking_points") or ["Introduce your GAF product lines."])[:3],
            recommended_approach=data.get("recommended_approach") or "",
            decision_makers=ground_decision_makers(data.get("decision_makers"), research),
            distance_miles=distance.distance_miles,
            distance_band=distance.distance_band,
            priority_index=compute_priority_index(lead_score, conv_score, distance.distance_band),
        )

    def _ask_model(self, prompt: str) -> dict:
        """Call Chat Completions in JSON mode and parse the reply."""
        completion = self._client.chat.completions.create(
            model=self._model,
            max_tokens=1200,
            temperature=0.3,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        usage = getattr(completion, "usage", None)
        logger.info("enrich.done model=%s prompt_tokens=%s completion_tokens=%s", self._model,
                    getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None))
        data = self._parse((completion.choices[0].message.content or "").strip())
        if not isinstance(data, dict):
            raise ValueError("Enrichment reply was not a JSON object")
        return data

    async def enrich_async(
        self,
        contractor: ContractorRecord,
        research: dict,
        search_postal_code: str = "",
    ) -> LeadInsight:
        """Async wrapper around enrich() for use in async pipeline contexts.

        The OpenAI SDK client used here is synchronous, so this offloads the call to a
        thread pool executor to avoid blocking the event loop.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self.enrich, contractor, research, search_postal_code
        )

    @staticmethod
    def _parse(raw: str) -> dict:
        """Parse the model's JSON response, stripping markdown fences if present.

        Models occasionally wrap JSON in ```json``` blocks despite instructions
        not to. This method handles both clean and fenced responses before raising.
        """
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
            return json.loads(cleaned)
