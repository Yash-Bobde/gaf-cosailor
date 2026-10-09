"""Tests for ScoringService and compute_priority_index (services/scorer.py).

Organised into four test classes mirroring the four public methods:
  TestLeadBaseline           — compute_lead_baseline()
  TestConvertibilityBaseline — compute_convertibility_baseline()
  TestDistance               — compute_distance()
  TestPriorityIndex          — compute_priority_index()
"""
import pytest


class TestLeadBaseline:
    def test_master_elite_cert_gives_10_points(self):
        """Master Elite is the highest GAF tier and maps to 10.0 cert points."""
        from app.services.scorer import ScoringService
        from app.models.lead import ContractorRecord

        svc = ScoringService()
        c = ContractorRecord(
            company_name="Test",
            certifications=["GAF Master Elite"],
            rating=None,
            review_count=None,
        )
        result = svc.compute_lead_baseline(c)
        assert result.cert_points == 10.0

    def test_certified_gives_7_points(self):
        """GAF Certified Contractor tier maps to 7.0 cert points."""
        from app.services.scorer import ScoringService
        from app.models.lead import ContractorRecord

        svc = ScoringService()
        c = ContractorRecord(
            company_name="Test",
            certifications=["GAF Certified Contractor"],
        )
        result = svc.compute_lead_baseline(c)
        assert result.cert_points == 7.0

    def test_no_certification_gives_2_points(self):
        """Uncertified contractors receive a minimal 2.0 points (not zero)."""
        from app.services.scorer import ScoringService
        from app.models.lead import ContractorRecord

        svc = ScoringService()
        c = ContractorRecord(company_name="Test", certifications=[])
        result = svc.compute_lead_baseline(c)
        assert result.cert_points == 2.0

    def test_rating_converts_to_0_to_10_scale(self):
        """A 4.8-star rating doubles to 9.6 on the 0–10 scale."""
        from app.services.scorer import ScoringService
        from app.models.lead import ContractorRecord

        svc = ScoringService()
        c = ContractorRecord(company_name="Test", rating=4.8)
        result = svc.compute_lead_baseline(c)
        assert result.rating_points == pytest.approx(9.6)

    def test_missing_rating_gives_neutral_5_points(self):
        """A missing star rating defaults to 5.0 (neutral) rather than zero."""
        from app.services.scorer import ScoringService
        from app.models.lead import ContractorRecord

        svc = ScoringService()
        c = ContractorRecord(company_name="Test", rating=None)
        result = svc.compute_lead_baseline(c)
        assert result.rating_points == 5.0

    def test_review_count_capped_at_50(self):
        """100 reviews still yields the maximum 10.0 review points (cap at 50)."""
        from app.services.scorer import ScoringService
        from app.models.lead import ContractorRecord

        svc = ScoringService()
        c = ContractorRecord(company_name="Test", review_count=100)
        result = svc.compute_lead_baseline(c)
        assert result.review_points == 10.0

    def test_partial_review_count(self):
        """25 reviews is exactly half the cap (50), yielding 5.0 review points."""
        from app.services.scorer import ScoringService
        from app.models.lead import ContractorRecord

        svc = ScoringService()
        c = ContractorRecord(company_name="Test", review_count=25)
        result = svc.compute_lead_baseline(c)
        assert result.review_points == pytest.approx(5.0)

    def test_size_points_always_neutral(self):
        """size_points is always 5.0 because GAF provides no revenue/headcount data."""
        from app.services.scorer import ScoringService
        from app.models.lead import ContractorRecord

        svc = ScoringService()
        c = ContractorRecord(company_name="Test")
        result = svc.compute_lead_baseline(c)
        assert result.size_points == 5.0

    def test_full_baseline_calculation_master_elite(self):
        """Full weighted calculation for a Master Elite contractor with strong reviews."""
        from app.services.scorer import ScoringService
        from app.models.lead import ContractorRecord

        svc = ScoringService()
        c = ContractorRecord(
            company_name="Acme Roofing",
            certifications=["GAF Master Elite"],
            rating=4.8,
            review_count=47,
        )
        result = svc.compute_lead_baseline(c)
        # cert=10*0.4 + size=5*0.25 + rating=9.6*0.25 + reviews=9.4*0.1
        # = 4.0 + 1.25 + 2.4 + 0.94 = 8.59 → rounds to 8.6
        assert result.baseline == pytest.approx(8.6, abs=0.1)
        assert 1 <= result.baseline <= 10

    def test_baseline_clamped_to_1_minimum(self):
        """A contractor with no certifications, zero rating, and zero reviews still scores at least 1."""
        from app.services.scorer import ScoringService
        from app.models.lead import ContractorRecord

        svc = ScoringService()
        c = ContractorRecord(
            company_name="Tiny Co",
            certifications=[],
            rating=0.0,
            review_count=0,
        )
        result = svc.compute_lead_baseline(c)
        assert result.baseline >= 1.0


class TestConvertibilityBaseline:
    def test_empty_research_returns_all_false_baseline_1(self):
        """No research text means no signals detected and a minimum baseline of 1."""
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_convertibility_baseline(None)
        assert result.portfolio_gap_detected is False
        assert result.growth_signal_detected is False
        assert result.cert_momentum_detected is False
        assert result.baseline == 1.0

    def test_empty_string_research_returns_baseline_1(self):
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_convertibility_baseline("")
        assert result.baseline == 1.0

    def test_competitor_brand_detected_as_portfolio_gap(self):
        """Mentions of Owens Corning trigger the portfolio gap signal."""
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_convertibility_baseline(
            "The company uses Owens Corning and IKO shingles."
        )
        assert result.portfolio_gap_detected is True

    def test_exclusive_gaf_suppresses_portfolio_gap(self):
        """Exclusive GAF language overrides the portfolio gap even when a competitor is mentioned."""
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_convertibility_baseline(
            "They exclusively GAF products and also mentioned CertainTeed once."
        )
        assert result.portfolio_gap_detected is False

    def test_growth_keywords_detected(self):
        """'expanding' and 'hiring' keywords trigger the growth signal."""
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_convertibility_baseline(
            "The company is expanding into new markets and hiring aggressively."
        )
        assert result.growth_signal_detected is True

    def test_cert_momentum_detected(self):
        """'recently certified' triggers the certification momentum signal."""
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_convertibility_baseline(
            "They recently certified as a GAF Master Elite contractor."
        )
        assert result.cert_momentum_detected is True

    def test_all_three_signals_gives_baseline_10(self):
        """All three signals present → maximum baseline of 10."""
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_convertibility_baseline(
            "They use Owens Corning and are expanding. They recently certified."
        )
        assert result.portfolio_gap_detected is True
        assert result.growth_signal_detected is True
        assert result.cert_momentum_detected is True
        assert result.baseline == 10.0

    def test_portfolio_gap_only_gives_baseline_4(self):
        """Portfolio gap alone (40% weight) → 10 × 0.40 = 4.0 baseline."""
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_convertibility_baseline(
            "They use Owens Corning shingles."
        )
        assert result.portfolio_gap_detected is True
        assert result.growth_signal_detected is False
        assert result.cert_momentum_detected is False
        # 10 * 0.40 = 4.0
        assert result.baseline == 4.0

    def test_growth_only_gives_baseline_4(self):
        """Growth signal alone (35% weight) → 10 × 0.35 = 3.5 → round(3.5) = 4 (banker's rounding)."""
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_convertibility_baseline(
            "They are hiring and expanding rapidly."
        )
        # 10 * 0.35 = 3.5 → round(3.5) = 4 (Python banker's rounding)
        assert result.growth_signal_detected is True
        assert result.baseline == 4.0

    def test_baseline_never_below_1(self):
        """Research text with no signals still returns a minimum baseline of 1."""
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_convertibility_baseline("No signals here at all.")
        assert result.baseline >= 1.0


class TestDistance:
    def test_missing_contractor_postal_returns_near_band(self):
        """Missing contractor ZIP defaults to 'near' with no distance value."""
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_distance(None, "10013")
        assert result.distance_miles is None
        assert result.distance_band == "near"

    def test_missing_search_postal_returns_near_band(self):
        """Missing search origin ZIP defaults to 'near' with no distance value."""
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_distance("10013", "")
        assert result.distance_miles is None
        assert result.distance_band == "near"

    def test_same_postal_code_gives_near_band(self, mock_pgeocode_same):
        """Identical ZIPs resolve to ~0 miles, which is in the 'near' band."""
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_distance("10013", "10013")
        assert result.distance_band == "near"
        assert result.distance_miles == pytest.approx(0.0, abs=1.0)

    def test_near_band_0_to_25_miles(self, mock_pgeocode_near):
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_distance("10013", "10001")
        assert result.distance_band == "near"
        assert result.distance_miles is not None
        assert result.distance_miles <= 25.0

    def test_mid_band_26_to_50_miles(self, mock_pgeocode_mid):
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_distance("07001", "10013")
        assert result.distance_band == "mid"
        assert 25.0 < result.distance_miles <= 50.0

    def test_far_band_over_50_miles(self, mock_pgeocode_far):
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_distance("06001", "10013")
        assert result.distance_band == "far"
        assert result.distance_miles > 50.0

    def test_invalid_postal_returns_near_fallback(self, mock_pgeocode_invalid):
        """An unrecognised ZIP that returns NaN coordinates falls back to 'near' band."""
        from app.services.scorer import ScoringService

        svc = ScoringService()
        result = svc.compute_distance("99999", "10013")
        assert result.distance_band == "near"
        assert result.distance_miles is None


class TestPriorityIndex:
    def test_near_band_no_modifier(self):
        """Near band modifier is 1.00 so priority_index equals the raw average."""
        from app.services.scorer import compute_priority_index

        result = compute_priority_index(9, 8, "near")
        assert result == pytest.approx(8.5)

    def test_mid_band_applies_0_95_modifier(self):
        """Mid band modifier is 0.95: (9+8)/2 × 0.95 = 8.075."""
        from app.services.scorer import compute_priority_index

        result = compute_priority_index(9, 8, "mid")
        assert result == pytest.approx(8.075)

    def test_far_band_applies_0_90_modifier(self):
        """Far band modifier is 0.90: (9+8)/2 × 0.90 = 7.65."""
        from app.services.scorer import compute_priority_index

        result = compute_priority_index(9, 8, "far")
        assert result == pytest.approx(7.65)

    def test_unknown_band_defaults_to_no_modifier(self):
        """An unrecognised distance band defaults to modifier 1.0."""
        from app.services.scorer import compute_priority_index

        result = compute_priority_index(8, 6, "unknown")
        assert result == pytest.approx(7.0)
