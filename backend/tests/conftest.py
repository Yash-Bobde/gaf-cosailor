"""Shared pytest fixtures for the Cosailor Insights test suite.

Provides a realistic ContractorRecord (sample_contractor), a complete
enriched lead DB row (sample_lead_row), and five pgeocode mock fixtures
that simulate different distance scenarios without hitting the internet.
"""
import os

# Tests must never reach a real database or paid API by accident: force dummy
# credentials BEFORE app.config is imported (env vars beat backend/.env).
# Opt-in live tests read real values explicitly — see tests/test_live_opt_in.py.
for _name, _dummy in (("SUPABASE_URL", "http://127.0.0.1:9"), ("SUPABASE_KEY", "test-key"),
                      ("OPENAI_API_KEY", "sk-test-dummy"),
                      ("PERPLEXITY_API_KEY", "pplx-test-dummy")):
    os.environ[_name] = _dummy

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import patch


@pytest.fixture
def sample_contractor():
    """A fully-populated ContractorRecord representing a Master Elite contractor in NYC."""
    from app.models.lead import ContractorRecord
    return ContractorRecord(
        company_name="Acme Roofing Inc",
        city="New York",
        state="NY",
        postal_code="10013",
        country_code="us",
        phone="212-555-0100",
        website="https://acmeroofing.com",
        certifications=["GAF Master Elite"],
        rating=4.8,
        review_count=47,
    )


@pytest.fixture
def sample_lead_row():
    """A complete enriched lead row as returned by the Supabase leads table."""
    return {
        "id": str(uuid4()),
        "company_name": "Acme Roofing Inc",
        "city": "New York",
        "state": "NY",
        "postal_code": "10013",
        "country_code": "us",
        "phone": "212-555-0100",
        "website": "https://acmeroofing.com",
        "certifications": ["GAF Master Elite"],
        "rating": 4.8,
        "review_count": 47,
        "lead_score": 9,
        "score_rationale": "Master Elite certified, strong reviews",
        "convertibility_score": 7,
        "convertibility_rationale": "Competitor brands detected, growth signals present.",
        "distance_miles": 5.2,
        "distance_band": "near",
        "priority_index": 8.0,
        "ai_summary": "Acme Roofing is a high-priority lead.",
        "talking_points": ["Point 1", "Point 2", "Point 3"],
        "recommended_approach": "Call the owner directly.",
        "status": "enriched",
        "research_summary": "Strong web presence.",
        "research_sources": [],
        "error_message": None,
        "enriched_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _make_postal_result(lat: float, lon: float):
    """Create a mock pgeocode query result with given lat/lon."""
    result = MagicMock()
    result.latitude = lat
    result.longitude = lon
    return result


@pytest.fixture
def mock_pgeocode_same():
    """Both postal codes map to the same location (0 miles apart)."""
    with patch("app.services.scorer.pgeocode") as mock_pg:
        nomi = MagicMock()
        nomi.query_postal_code.return_value = _make_postal_result(40.7128, -74.0060)
        mock_pg.Nominatim.return_value = nomi
        yield mock_pg


@pytest.fixture
def mock_pgeocode_near():
    """Two postal codes ~1 mile apart — Near band."""
    with patch("app.services.scorer.pgeocode") as mock_pg:
        nomi = MagicMock()
        nomi.query_postal_code.side_effect = [
            _make_postal_result(40.7128, -74.0060),   # contractor
            _make_postal_result(40.7178, -74.0020),   # search origin
        ]
        mock_pg.Nominatim.return_value = nomi
        yield mock_pg


@pytest.fixture
def mock_pgeocode_mid():
    """Two postal codes ~30 miles apart — Mid band."""
    with patch("app.services.scorer.pgeocode") as mock_pg:
        nomi = MagicMock()
        nomi.query_postal_code.side_effect = [
            _make_postal_result(40.4000, -74.4000),   # contractor (~30 mi from NYC)
            _make_postal_result(40.7128, -74.0060),   # search origin (NYC)
        ]
        mock_pg.Nominatim.return_value = nomi
        yield mock_pg


@pytest.fixture
def mock_pgeocode_far():
    """Two postal codes ~100 miles apart — Far band."""
    with patch("app.services.scorer.pgeocode") as mock_pg:
        nomi = MagicMock()
        nomi.query_postal_code.side_effect = [
            _make_postal_result(41.7658, -72.6851),   # contractor (~100 mi away)
            _make_postal_result(40.7128, -74.0060),   # search origin
        ]
        mock_pg.Nominatim.return_value = nomi
        yield mock_pg


@pytest.fixture
def mock_pgeocode_invalid():
    """Postal code lookup returns NaN — should fall back gracefully to 'near' band."""
    import math
    with patch("app.services.scorer.pgeocode") as mock_pg:
        nomi = MagicMock()
        nomi.query_postal_code.side_effect = [
            _make_postal_result(math.nan, math.nan),  # invalid / unrecognised ZIP
            _make_postal_result(40.7128, -74.0060),
        ]
        mock_pg.Nominatim.return_value = nomi
        yield mock_pg
