"""Tests for ContractorResearcher (services/researcher.py).

Verifies that the Perplexity Agent API output is correctly parsed into a
{summary, sources} dict — citation markers become inline links to the cited search
results — and that API errors raise ResearchError (never an empty "successful"
result). Retry and failure semantics: test_research_failures.py.
"""
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

MOCK_PERPLEXITY_RESPONSE = {
    "object": "response",
    "status": "completed",
    "output": [
        {
            "type": "search_results",
            "results": [
                {"id": 1, "url": "https://www.bbb.org/acme", "title": "Acme BBB"},
                {"id": 2, "url": "https://yelp.com/acme", "title": "Acme Yelp"},
                {"id": 3, "url": "https://never-cited.example", "title": "Unused"},
            ],
        },
        {
            "type": "message",
            "content": [{
                "type": "output_text",
                "text": "Acme Roofing is strong in NYC. A+ BBB rating [1]. Uses GAF products [1][2].",
                "annotations": [],
            }],
        },
    ],
    "usage": {"input_tokens": 900, "output_tokens": 300, "total_tokens": 1200,
              "cost": {"total_cost": 0.006, "currency": "USD"}},
}


def _client_returning(payload):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = payload
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.mark.asyncio
async def test_researcher_returns_summary_and_sources(sample_contractor):
    """A successful Perplexity response maps to a cited summary and de-duplicated sources."""
    from app.services.researcher import ContractorResearcher

    mock_client = _client_returning(MOCK_PERPLEXITY_RESPONSE)
    with patch("app.services.researcher.httpx.AsyncClient", return_value=mock_client):
        researcher = ContractorResearcher(api_key="test-key")
        result = await researcher.research(sample_contractor)

    assert "Acme Roofing" in result["summary"]
    assert result["sources"] == ["https://www.bbb.org/acme", "https://yelp.com/acme"]
    assert result["usage"] == {"input_tokens": 900, "output_tokens": 300,
                               "total_tokens": 1200, "cost_usd": 0.006}


@pytest.mark.asyncio
async def test_researcher_posts_preset_and_prompt_to_agent_api(sample_contractor):
    from app.services.researcher import ContractorResearcher

    mock_client = _client_returning(MOCK_PERPLEXITY_RESPONSE)
    with patch("app.services.researcher.httpx.AsyncClient", return_value=mock_client):
        await ContractorResearcher(api_key="test-key", preset="low").research(sample_contractor)

    url = mock_client.post.await_args.args[0]
    kwargs = mock_client.post.await_args.kwargs
    assert url == "https://api.perplexity.ai/v1/agent"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["json"]["preset"] == "low"
    assert "Acme Roofing Inc" in kwargs["json"]["input"]
    # The instructions ask for numbered citation markers, which become source links.
    assert "[2]" in kwargs["json"]["instructions"]


def test_citation_markers_become_inline_links_to_cited_results():
    from app.services.researcher import _parse_response

    result = _parse_response(MOCK_PERPLEXITY_RESPONSE)

    assert "A+ BBB rating ([bbb.org](https://www.bbb.org/acme))." in result["summary"]
    assert ("GAF products ([bbb.org](https://www.bbb.org/acme), "
            "[yelp.com](https://yelp.com/acme)).") in result["summary"]
    assert "[1]" not in result["summary"]
    assert "https://never-cited.example" not in result["sources"]


def test_web_markers_unknown_ids_and_annotations():
    """[web:n] markers resolve too; unknown ids stay as written; url_citation annotations count."""
    from app.services.researcher import _parse_response

    payload = {"output": [
        {"type": "search_results", "results": [{"id": "1", "url": "https://acme.example/team"}]},
        {"type": "message", "content": [{
            "type": "output_text",
            "text": "Owner: Jane Doe [web:1]. Founded 1990 [7].",
            "annotations": [{"type": "url_citation", "url": "https://bbb.org/acme"}],
        }]},
    ]}
    result = _parse_response(payload)

    assert "Jane Doe ([acme.example](https://acme.example/team))." in result["summary"]
    assert "Founded 1990 [7]." in result["summary"]
    assert result["sources"] == ["https://acme.example/team", "https://bbb.org/acme"]


def test_failed_run_raises_research_error():
    from app.services.errors import ResearchError
    from app.services.researcher import _parse_response

    with pytest.raises(ResearchError, match="failed"):
        _parse_response({"status": "failed", "output": [],
                         "error": {"message": "upstream error"}})


@pytest.mark.asyncio
async def test_researcher_raises_research_error_on_api_error(sample_contractor):
    """A network failure that outlasts retries raises ResearchError, not an empty result."""
    from tenacity import wait_none
    from app.services.errors import ResearchError
    from app.services.researcher import ContractorResearcher

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("network error"))

    with patch("app.services.researcher.httpx.AsyncClient", return_value=mock_client):
        researcher = ContractorResearcher(api_key="test-key", max_attempts=2, wait=wait_none())
        with pytest.raises(ResearchError):
            await researcher.research(sample_contractor)


def test_research_prompt_asks_for_decision_makers_and_uses_profile_url(sample_contractor):
    from app.services.researcher import _build_prompt

    c = sample_contractor.model_copy(update={"gaf_profile_url": "https://www.gaf.com/x/acme-1"})
    prompt = _build_prompt(c)
    assert "decision-makers" in prompt.lower()
    assert "https://www.gaf.com/x/acme-1" in prompt


@pytest.mark.parametrize("status,retries", [(429, True), (503, True), (401, False), (400, False)])
def test_only_rate_limit_and_server_errors_are_retried(status, retries):
    import httpx
    from app.services.researcher import _is_retryable

    req = httpx.Request("POST", "https://api.perplexity.ai/v1/agent")
    err = httpx.HTTPStatusError("x", request=req, response=httpx.Response(status, request=req))
    assert _is_retryable(err) is retries


def test_perplexity_keys_are_redacted_from_error_text():
    from app.services.errors import sanitize_error

    assert "pplx-" not in sanitize_error("bad key pplx-AbCdEf123456789 rejected")
