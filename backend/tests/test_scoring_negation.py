"""Regression fixtures for opportunity-signal detection (scorer.compute_convertibility_baseline).

Keyword matching alone is fooled by negated or boilerplate phrasing that web
research routinely produces ("No recent growth signals or new markets were
found"). These fixtures pin down the negation-aware behaviour.
"""
import pytest

from app.services.scorer import ScoringService

_svc = ScoringService()


def _signals(text: str) -> tuple[bool, bool, bool]:
    c = _svc.compute_convertibility_baseline(text)
    return c.portfolio_gap_detected, c.growth_signal_detected, c.cert_momentum_detected


# ── Competitor brands (portfolio gap) ─────────────────────────────────────

@pytest.mark.parametrize("text", [
    "They install Owens Corning Duration shingles on most jobs.",
    "Crews work with CertainTeed and GAF products.",
    "Reviews mention IKO Cambridge shingles.",
])
def test_positive_competitor_mentions_detect_a_portfolio_gap(text):
    assert _signals(text)[0] is True


@pytest.mark.parametrize("text", [
    "They do not use Owens Corning products.",
    "The company no longer installs CertainTeed shingles.",
    "They switched from Tamko to GAF in 2021.",
    "No evidence that they use Malarkey or IKO.",
    "They exclusively install GAF shingles, not Owens Corning.",
])
def test_negated_competitor_mentions_do_not_detect_a_gap(text):
    assert _signals(text)[0] is False


def test_brand_names_match_whole_words_only():
    assert _signals("Mikolaj Nikon handles strategic atlases.")[0] is False


# ── Growth ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "Acme is hiring roofers for a second crew.",
    "They opened a new location in Hoboken this year.",
    "The company is expanding into commercial work.",
])
def test_positive_growth_statements_are_detected(text):
    assert _signals(text)[1] is True


@pytest.mark.parametrize("text", [
    "No recent growth signals or new markets were found.",
    "There is no indication they are hiring.",
    "They are not expanding at this time.",
    "Information on new locations is unavailable.",
])
def test_negated_or_boilerplate_growth_is_not_detected(text):
    assert _signals(text)[1] is False


def test_negation_in_one_sentence_does_not_cancel_a_positive_in_another():
    text = "They do not use Owens Corning. They are hiring two estimators."
    gap, growth, _ = _signals(text)
    assert (gap, growth) == (False, True)


# ── Baseline invariants ───────────────────────────────────────────────────

def test_empty_research_is_baseline_one():
    assert _svc.compute_convertibility_baseline("").baseline == 1.0
    assert _svc.compute_convertibility_baseline(None).baseline == 1.0


def test_all_signals_give_max_baseline():
    text = ("They install Owens Corning shingles. They are hiring. "
            "They recently became GAF certified.")
    assert _svc.compute_convertibility_baseline(text).baseline == 10.0
