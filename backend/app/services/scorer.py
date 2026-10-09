"""Deterministic scoring engine for lead prioritization.

ScoringService produces two independent baselines from structured data:

  compute_lead_baseline()           — weighted quality score derived from
                                      certifications, star rating, and review count
  compute_convertibility_baseline() — rules-based OPPORTUNITY score from signals in
                                      the web research (portfolio gap, growth, cert
                                      momentum); negation-aware, sentence by sentence
  compute_distance()                — haversine distance between contractor ZIP and
                                      the search origin ZIP

compute_priority_index() combines both scores with a distance modifier into a
single sortable float used for dashboard ordering.

All baselines are passed to LeadEnricher as anchors; the model may adjust each
score by at most ±1 but cannot exceed those bounds.

These are heuristic PRIORITY scores, not validated conversion probabilities —
no labelled sales-outcome data exists to calibrate them. Known behaviour: the
fit baseline saturates near 9 for Master Elite contractors with strong ratings
(cert 10×0.40 + neutral size 5×0.25 + rating ~9.6×0.25 + reviews 10×0.10 ≈ 8.7),
so fit separates certified from uncertified contractors far better than it
ranks strong contractors against each other. The field name
`convertibility_score` is kept for API/DB compatibility; the UI calls it
"Opportunity".
"""
import math
import re
from dataclasses import dataclass
from typing import Optional

import pgeocode


# ── Data containers ──────────────────────────────────────────────────────────

@dataclass
class LeadScoreComponents:
    """Intermediate values produced by compute_lead_baseline().

    size_points is always 5.0 (neutral) because revenue/headcount is not
    available from the GAF directory. The model adjusts the final lead_score
    by up to ±1 based on the web research context.
    """
    cert_points: float
    size_points: float   # always 5.0 from Python; the model adjusts final score ±1
    rating_points: float
    review_points: float
    baseline: float      # weighted sum, clamped 1–10


@dataclass
class ConvertibilityComponents:
    """Boolean signal flags and the resulting baseline from compute_convertibility_baseline()."""
    portfolio_gap_detected: bool
    growth_signal_detected: bool
    cert_momentum_detected: bool
    baseline: float      # weighted sum, clamped 1–10


@dataclass
class DistanceResult:
    """Haversine distance result from compute_distance()."""
    distance_miles: Optional[float]
    distance_band: str   # 'near' | 'mid' | 'far'


# ── Constants ─────────────────────────────────────────────────────────────────

# GAF certification tier → raw point value (out of 10, weight 40% in lead baseline)
_CERT_POINTS: dict[str, float] = {
    "master elite": 10.0,
    "certified":     7.0,
}
_CERT_DEFAULT = 2.0  # uncertified contractors receive a minimal score, not zero

# Competitor brand names used to detect a portfolio-gap opportunity (whole words)
_COMPETITOR_BRANDS = [
    "owens corning", "certainteed", "iko", "tamko", "atlas", "malarkey",
]
# Regex to detect exclusivity language that negates the portfolio gap signal
_EXCLUSIVE_GAF = re.compile(r"exclusive(?:ly)?\s+(?:\w+\s+)?gaf|gaf\s+exclusive", re.IGNORECASE)

# Keywords indicating recent hiring or market expansion (growth signal)
_GROWTH_KEYWORDS = [
    "hiring", "expanding", "new location", "new market", "growing", "opened",
]

# Phrases suggesting the contractor recently earned or upgraded a GAF certification
_CERT_MOMENTUM_KEYWORDS = [
    "recently certified", "just became", "newly certified",
    "recently became", "just certified", "new certification", "newly became",
]

# A sentence containing one of these cues does not count as evidence for a signal:
# research routinely says "No recent growth signals or new markets were found".
_NEGATION = re.compile(
    r"\b(?:not|no|never|none|nor|without|no longer|stopped|switched from|moved away from|"
    r"replaced|unavailable|unknown|unclear|lack of|absence of)\b|n't\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")


def _keyword_patterns(keywords: list[str]) -> list[re.Pattern]:
    """Whole-word, plural-tolerant patterns ('iko' must not match 'Nikon')."""
    return [re.compile(rf"\b{re.escape(k)}s?\b", re.IGNORECASE) for k in keywords]


_COMPETITOR_PATTERNS = _keyword_patterns(_COMPETITOR_BRANDS)
_GROWTH_PATTERNS = _keyword_patterns(_GROWTH_KEYWORDS)
_CERT_MOMENTUM_PATTERNS = _keyword_patterns(_CERT_MOMENTUM_KEYWORDS)


def _affirmed(text: str, patterns: list[re.Pattern]) -> bool:
    """True when some sentence mentions a keyword WITHOUT a negation cue in that sentence."""
    for sentence in _SENTENCE_SPLIT.split(text):
        if any(p.search(sentence) for p in patterns) and not _NEGATION.search(sentence):
            return True
    return False

# Distance band → priority_index multiplier (nearer contractors rank higher)
_DISTANCE_MODIFIER: dict[str, float] = {
    "near": 1.00,
    "mid":  0.95,
    "far":  0.90,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cert_points(certifications: list[str]) -> float:
    """Return raw certification points for the highest GAF tier present in the list."""
    if not certifications:
        return _CERT_DEFAULT
    cert_str = " ".join(certifications).lower()
    if "master elite" in cert_str:
        return _CERT_POINTS["master elite"]
    if "certified" in cert_str:
        return _CERT_POINTS["certified"]
    return _CERT_DEFAULT


def _rating_points(rating: Optional[float]) -> float:
    """Convert a 0–5 star rating to a 0–10 point scale. Returns neutral 5.0 when missing."""
    if rating is None:
        return 5.0  # neutral when missing
    return min(rating * 2.0, 10.0)


def _review_points(review_count: Optional[int]) -> float:
    """Score review volume on a 0–10 scale, capping at 50 reviews for full marks."""
    if not review_count:
        return 0.0
    return min((review_count / 50.0) * 10.0, 10.0)


# ── Service ───────────────────────────────────────────────────────────────────

class ScoringService:
    """Stateless service that computes lead and convertibility baselines."""

    def compute_lead_baseline(self, contractor) -> LeadScoreComponents:
        """Compute a weighted lead quality score from structured contractor attributes.

        Weights: certification 40%, company size 25%, star rating 25%, review count 10%.
        Size is always 5.0 (neutral) because revenue/headcount is not available from GAF;
        the model adjusts the final score (±1) using the web research context.
        """
        cert    = _cert_points(contractor.certifications)
        size    = 5.0  # neutral; the model adjusts based on research text
        rating  = _rating_points(contractor.rating)
        reviews = _review_points(contractor.review_count)

        raw = cert * 0.40 + size * 0.25 + rating * 0.25 + reviews * 0.10
        baseline = max(1.0, min(10.0, round(raw, 1)))

        return LeadScoreComponents(
            cert_points=cert,
            size_points=size,
            rating_points=rating,
            review_points=reviews,
            baseline=baseline,
        )

    def compute_convertibility_baseline(
        self, research_text: Optional[str]
    ) -> ConvertibilityComponents:
        """Detect opportunity signals in the web research text (negation-aware).

        Three binary signals are combined with fixed weights:
          - Portfolio gap (40%): competitor brands present with no GAF-exclusivity language
          - Growth signals (35%): keywords indicating expansion or hiring activity
          - Cert momentum (25%): phrases indicating a recently achieved GAF certification

        Returns a baseline of 1.0 when no research text is available.
        """
        if not research_text:
            return ConvertibilityComponents(
                portfolio_gap_detected=False,
                growth_signal_detected=False,
                cert_momentum_detected=False,
                baseline=1.0,
            )

        # Portfolio gap: an affirmed competitor-brand mention, no exclusive-GAF language
        has_competitor = _affirmed(research_text, _COMPETITOR_PATTERNS)
        has_exclusive = bool(_EXCLUSIVE_GAF.search(research_text))
        portfolio_gap = has_competitor and not has_exclusive

        growth = _affirmed(research_text, _GROWTH_PATTERNS)
        cert_momentum = _affirmed(research_text, _CERT_MOMENTUM_PATTERNS)

        raw = (
            (10.0 * 0.40 if portfolio_gap  else 0.0) +
            (10.0 * 0.35 if growth         else 0.0) +
            (10.0 * 0.25 if cert_momentum  else 0.0)
        )
        baseline = float(max(1, round(raw)))

        return ConvertibilityComponents(
            portfolio_gap_detected=portfolio_gap,
            growth_signal_detected=growth,
            cert_momentum_detected=cert_momentum,
            baseline=baseline,
        )

    def compute_distance(
        self, contractor_postal: Optional[str], search_postal: str
    ) -> DistanceResult:
        """Calculate the haversine distance between two US ZIP codes using pgeocode.

        Returns distance_band='near' with distance_miles=None when either postal
        code is missing, or when pgeocode returns NaN coordinates for unrecognised ZIPs.
        """
        if not contractor_postal or not search_postal:
            return DistanceResult(distance_miles=None, distance_band="near")

        try:
            nomi = pgeocode.Nominatim("us")
            dest   = nomi.query_postal_code(contractor_postal)
            origin = nomi.query_postal_code(search_postal)

            # Guard against NaN values (unrecognised postal codes)
            coords = [dest.latitude, dest.longitude, origin.latitude, origin.longitude]
            if any(math.isnan(float(v)) for v in coords):
                return DistanceResult(distance_miles=None, distance_band="near")

            # Haversine formula — earth radius 6371 km, converted to miles
            lat1 = math.radians(float(origin.latitude))
            lon1 = math.radians(float(origin.longitude))
            lat2 = math.radians(float(dest.latitude))
            lon2 = math.radians(float(dest.longitude))

            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = (
                math.sin(dlat / 2) ** 2
                + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            )
            miles = 6371 * 2 * math.asin(math.sqrt(a)) * 0.621371

            if miles <= 25:
                band = "near"
            elif miles <= 50:
                band = "mid"
            else:
                band = "far"

            return DistanceResult(distance_miles=round(miles, 2), distance_band=band)

        except Exception:
            return DistanceResult(distance_miles=None, distance_band="near")


def compute_priority_index(
    lead_score: int,
    convertibility_score: int,
    distance_band: str,
) -> float:
    """Combine lead and convertibility scores into a single sortable priority index.

    Formula: ((lead_score + convertibility_score) / 2) × distance_modifier

    Distance modifiers: near=1.00, mid=0.95, far=0.90.
    Defaults to modifier 1.0 for unrecognised band values.
    """
    modifier = _DISTANCE_MODIFIER.get(distance_band, 1.0)
    return round(((lead_score + convertibility_score) / 2) * modifier, 3)
