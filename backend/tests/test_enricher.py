"""Tests for LeadEnricher (services/enricher.py).

Covers JSON parsing (clean and fenced), score clamping, and correct
ScoringService delegation. All OpenAI API calls are mocked so these
tests run without credentials.
"""
import pytest
from unittest.mock import MagicMock, patch

# Representative OpenAI response used across multiple tests
MOCK_JSON = """{
  "lead_score": 9,
  "score_rationale": "Master Elite certified with strong reviews justifies top-tier score.",
  "convertibility_score": 7,
  "convertibility_rationale": "Competitor brands detected in research, growth signals present.",
  "ai_summary": "Acme Roofing is a top-tier GAF contractor in NYC with 47 5-star reviews. Master Elite status makes them ideal for distributor outreach.",
  "talking_points": [
    "As a Master Elite contractor you qualify for exclusive GAF volume rebates — let's review what's available.",
    "With 47 reviews at 4.8 stars your reputation is a competitive advantage — GAF warranty programs amplify this.",
    "Timberline HDZ demand is strong in NYC — your certification positions you to capture that market."
  ],
  "recommended_approach": "Open with a call to the owner referencing their Master Elite status. Lead with the rebate program then discuss new product availability."
}"""


def test_enricher_parses_clean_json(sample_contractor):
    """A clean JSON response from OpenAI is parsed into a valid LeadInsight."""
    from app.services.scorer import (
        LeadScoreComponents, ConvertibilityComponents, DistanceResult
    )
    from app.models.lead import LeadInsight

    mock_msg = MagicMock()
    mock_msg.choices = [MagicMock(message=MagicMock(content=MOCK_JSON))]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_msg

    mock_lead_comps = LeadScoreComponents(
        cert_points=10.0, size_points=5.0,
        rating_points=9.6, review_points=9.4, baseline=8.6,
    )
    mock_conv_comps = ConvertibilityComponents(
        portfolio_gap_detected=True, growth_signal_detected=True,
        cert_momentum_detected=False, baseline=7.5,
    )
    mock_distance = DistanceResult(distance_miles=5.2, distance_band="near")

    with patch("app.services.enricher.OpenAI", return_value=mock_client), \
         patch("app.services.enricher.ScoringService") as mock_scorer_cls:

        mock_scorer = MagicMock()
        mock_scorer_cls.return_value = mock_scorer
        mock_scorer.compute_lead_baseline.return_value = mock_lead_comps
        mock_scorer.compute_convertibility_baseline.return_value = mock_conv_comps
        mock_scorer.compute_distance.return_value = mock_distance

        from app.services.enricher import LeadEnricher
        enricher = LeadEnricher(api_key="test-key")
        insight = enricher.enrich(
            sample_contractor,
            {"summary": "Strong. Uses Owens Corning. Expanding.", "sources": []},
            search_postal_code="10013",
        )

    assert isinstance(insight, LeadInsight)
    assert insight.lead_score == 9
    assert insight.convertibility_score == 7
    assert insight.distance_band == "near"
    assert insight.distance_miles == pytest.approx(5.2)
    assert len(insight.talking_points) == 3
    assert insight.priority_index > 0


def test_enricher_strips_markdown_fences(sample_contractor):
    """A JSON response wrapped in ```json``` fences is parsed correctly."""
    from app.services.scorer import (
        LeadScoreComponents, ConvertibilityComponents, DistanceResult
    )

    fenced = f"```json\n{MOCK_JSON}\n```"
    mock_msg = MagicMock()
    mock_msg.choices = [MagicMock(message=MagicMock(content=fenced))]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_msg

    mock_lead_comps = LeadScoreComponents(
        cert_points=10.0, size_points=5.0,
        rating_points=9.6, review_points=9.4, baseline=8.6,
    )
    mock_conv_comps = ConvertibilityComponents(
        portfolio_gap_detected=False, growth_signal_detected=False,
        cert_momentum_detected=False, baseline=1.0,
    )
    mock_distance = DistanceResult(distance_miles=None, distance_band="near")

    with patch("app.services.enricher.OpenAI", return_value=mock_client), \
         patch("app.services.enricher.ScoringService") as mock_scorer_cls:

        mock_scorer = MagicMock()
        mock_scorer_cls.return_value = mock_scorer
        mock_scorer.compute_lead_baseline.return_value = mock_lead_comps
        mock_scorer.compute_convertibility_baseline.return_value = mock_conv_comps
        mock_scorer.compute_distance.return_value = mock_distance

        from app.services.enricher import LeadEnricher
        enricher = LeadEnricher(api_key="test-key")
        insight = enricher.enrich(sample_contractor, {"summary": "Strong."}, search_postal_code="10013")

    assert insight.lead_score == 9


def test_enricher_clamps_lead_score_to_baseline_plus_one(sample_contractor):
    """OpenAI returns lead_score=15 (out of range) — must be clamped to baseline+1."""
    import json
    from app.services.scorer import (
        LeadScoreComponents, ConvertibilityComponents, DistanceResult
    )

    bad = json.dumps({
        "lead_score": 15,
        "score_rationale": "r",
        "convertibility_score": 5,
        "convertibility_rationale": "c",
        "ai_summary": "s",
        "talking_points": ["a", "b", "c"],
        "recommended_approach": "x",
    })
    mock_msg = MagicMock()
    mock_msg.choices = [MagicMock(message=MagicMock(content=bad))]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_msg

    # baseline=7 → max allowed lead_score = 8
    mock_lead_comps = LeadScoreComponents(
        cert_points=7.0, size_points=5.0,
        rating_points=7.0, review_points=5.0, baseline=7.0,
    )
    mock_conv_comps = ConvertibilityComponents(
        portfolio_gap_detected=False, growth_signal_detected=False,
        cert_momentum_detected=False, baseline=1.0,
    )
    mock_distance = DistanceResult(distance_miles=None, distance_band="near")

    with patch("app.services.enricher.OpenAI", return_value=mock_client), \
         patch("app.services.enricher.ScoringService") as mock_scorer_cls:

        mock_scorer = MagicMock()
        mock_scorer_cls.return_value = mock_scorer
        mock_scorer.compute_lead_baseline.return_value = mock_lead_comps
        mock_scorer.compute_convertibility_baseline.return_value = mock_conv_comps
        mock_scorer.compute_distance.return_value = mock_distance

        from app.services.enricher import LeadEnricher
        enricher = LeadEnricher(api_key="test-key")
        insight = enricher.enrich(sample_contractor, {}, search_postal_code="10013")

    # baseline=7, max allowed = min(10, 7+1)=8
    assert insight.lead_score <= 8
    assert 1 <= insight.lead_score <= 10


def test_enricher_scorer_called_with_correct_args(sample_contractor):
    """ScoringService is called with the contractor and the correct research text."""
    from app.services.scorer import (
        LeadScoreComponents, ConvertibilityComponents, DistanceResult
    )

    mock_msg = MagicMock()
    mock_msg.choices = [MagicMock(message=MagicMock(content=MOCK_JSON))]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_msg

    mock_lead_comps = LeadScoreComponents(
        cert_points=10.0, size_points=5.0,
        rating_points=9.6, review_points=9.4, baseline=8.6,
    )
    mock_conv_comps = ConvertibilityComponents(
        portfolio_gap_detected=True, growth_signal_detected=True,
        cert_momentum_detected=False, baseline=7.5,
    )
    mock_distance = DistanceResult(distance_miles=5.2, distance_band="near")

    with patch("app.services.enricher.OpenAI", return_value=mock_client), \
         patch("app.services.enricher.ScoringService") as mock_scorer_cls:

        mock_scorer = MagicMock()
        mock_scorer_cls.return_value = mock_scorer
        mock_scorer.compute_lead_baseline.return_value = mock_lead_comps
        mock_scorer.compute_convertibility_baseline.return_value = mock_conv_comps
        mock_scorer.compute_distance.return_value = mock_distance

        from app.services.enricher import LeadEnricher
        enricher = LeadEnricher(api_key="test-key")
        enricher.enrich(
            sample_contractor,
            {"summary": "Research text.", "sources": []},
            search_postal_code="10001",
        )

    mock_scorer.compute_lead_baseline.assert_called_once_with(sample_contractor)
    mock_scorer.compute_convertibility_baseline.assert_called_once_with("Research text.")
    mock_scorer.compute_distance.assert_called_once_with(
        sample_contractor.postal_code, "10001"
    )


# ── Decision-maker grounding ──────────────────────────────────────────────

def _enrich_with(sample_contractor, model_json: dict, research: dict):
    """Run LeadEnricher.enrich with a mocked OpenAI reply and fixed scoring baselines."""
    import json
    from app.services.scorer import LeadScoreComponents, ConvertibilityComponents, DistanceResult
    from app.services.enricher import LeadEnricher

    mock_msg = MagicMock()
    mock_msg.choices = [MagicMock(message=MagicMock(content=json.dumps(model_json)))]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_msg

    with patch("app.services.enricher.OpenAI", return_value=mock_client), \
         patch("app.services.enricher.ScoringService") as scorer_cls:
        scorer = scorer_cls.return_value
        scorer.compute_lead_baseline.return_value = LeadScoreComponents(
            cert_points=7, size_points=5, rating_points=7, review_points=5, baseline=7.0)
        scorer.compute_convertibility_baseline.return_value = ConvertibilityComponents(
            portfolio_gap_detected=False, growth_signal_detected=False,
            cert_momentum_detected=False, baseline=5.0)
        scorer.compute_distance.return_value = DistanceResult(distance_miles=3.0, distance_band="near")
        enricher = LeadEnricher(api_key="test-key")
        return enricher.enrich(sample_contractor, research, search_postal_code="10013"), mock_client


_BASE_JSON = {
    "lead_score": 7, "score_rationale": "r", "convertibility_score": 5,
    "convertibility_rationale": "c", "ai_summary": "s",
    "talking_points": ["a", "b", "c"], "recommended_approach": "x",
}


def test_enricher_keeps_only_decision_makers_named_in_research(sample_contractor):
    """Names the model invents (not present in the web research) are dropped."""
    research = {
        "summary": "Acme is run by owner Maria  Lopez; operations are led by Dev Patel.",
        "sources": ["https://bbb.org/acme"],
    }
    insight, _ = _enrich_with(sample_contractor, {**_BASE_JSON, "decision_makers": [
        {"name": "Maria Lopez", "title": "Owner", "source_url": "https://bbb.org/acme"},
        {"name": "dev patel", "title": "Operations Manager", "source_url": "https://made-up.example"},
        {"name": "John Hallucinated", "title": "CEO", "source_url": None},
    ]}, research)

    names = [d.name for d in insight.decision_makers]
    assert names == ["Maria Lopez", "dev patel"]
    assert insight.decision_makers[0].source_url == "https://bbb.org/acme"
    assert insight.decision_makers[1].source_url is None   # not a real citation → dropped


def test_enricher_tolerates_missing_or_malformed_decision_makers(sample_contractor):
    research = {"summary": "No people named.", "sources": []}
    insight, _ = _enrich_with(sample_contractor, {**_BASE_JSON, "decision_makers": "none"}, research)
    assert insight.decision_makers == []

    insight, _ = _enrich_with(sample_contractor, _BASE_JSON, research)
    assert insight.decision_makers == []


def test_enricher_requests_json_mode_with_configured_model(sample_contractor):
    _, client = _enrich_with(sample_contractor, _BASE_JSON, {"summary": "", "sources": []})
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["model"] == "gpt-4o-mini"
    assert "decision_makers" in kwargs["messages"][0]["content"]
