"""Perplexity web research service for contractor intelligence gathering.

ContractorResearcher asks the Perplexity Agent API (POST /v1/agent) for
publicly available B2B intelligence about one contractor: brands used, size,
reputation, growth signals and the people who make purchasing decisions.
The "fast" preset is Perplexity's documented replacement for the retired
Sonar model: one web-search step, then an answer.

Perplexity cites its sources as numbered markers ("[1]", or "[web:1]" on the
deeper presets) whose numbers are the ids of the returned search results. Each
marker is rewritten as an inline markdown link to that result, so the stored
summary reads like a cited note and the enricher can attribute people to a
real source URL. Only results the answer actually cites are kept as sources.

Concurrency is owned by the pipeline (one call per lead, bounded by a
semaphore). This service retries only transient failures — HTTP 429, 5xx and
network errors — with exponential backoff. Anything that yields no usable
evidence (a terminal HTTP error, exhausted retries, a failed run, an empty or
malformed reply) raises ResearchError: the pipeline then marks that one lead
failed instead of enriching it from nothing.
"""
import logging
import re
from urllib.parse import urlparse

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.models.lead import ContractorRecord
from app.services.errors import ResearchError

logger = logging.getLogger(__name__)

_AGENT_URL = "https://api.perplexity.ai/v1/agent"

# A run of adjacent citation markers, e.g. "[1]", "[1][3]" or "[web:2]".
_MARKER_RUN = re.compile(r"(?:\[(?:web:)?\d+\])+")
_MARKER_ID = re.compile(r"\[(?:web:)?(\d+)\]")

# System prompt keeps research responses factual, sales-relevant and cited: every
# fact carries the numbered marker of its search result, which _cite() turns into a link.
_SYSTEM = """You are a B2B sales research assistant for a roofing materials distributor.
Gather factual, verifiable intelligence about roofing contractors for sales outreach.
Be concise. Only state facts you found in search results; never guess names.
Cite every fact with the number of the search result it came from, in square brackets,
e.g. "Founded in 1996 [2]." or "Owner: Jane Doe [1][3]." Do not write URLs yourself."""


def _build_prompt(c: ContractorRecord) -> str:
    """Format the research prompt with every identity hint we have for the contractor."""
    location = f"{c.city}, {c.state}" if c.city else c.postal_code or "unknown"
    certs = ", ".join(c.certifications) if c.certifications else "none"
    return f"""Research this roofing contractor for a sales team at a GAF roofing distributor:

Company: {c.company_name}
Location: {location}
Phone: {c.phone or 'unknown'}
Website: {c.website or 'not provided'}
GAF profile: {c.gaf_profile_url or 'not provided'}
GAF Certifications: {certs}

Provide briefly:
1. Roofing brands/products they currently use or advertise
2. Approximate company size (employees/revenue tier) and years in business
3. Online reputation (BBB, Google review sentiment)
4. Any recent growth signals or new markets
5. Decision-makers: the owner/founder, president or purchasing/operations lead —
   full name and title exactly as published (e.g. on their website, BBB or LinkedIn)
If information is unavailable, say so briefly. Do not invent people."""


def _is_retryable(exc: BaseException) -> bool:
    """Retry only rate limits and server errors — a 400/401 will never succeed."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


def _search_results(output: list) -> dict[str, str]:
    """Map each search-result id (as a string) to its URL, across all search steps."""
    results: dict[str, str] = {}
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "search_results":
            continue
        for result in item.get("results") or []:
            if not isinstance(result, dict):
                continue
            url = result.get("url")
            if result.get("id") is not None and isinstance(url, str) and url.startswith("http"):
                results.setdefault(str(result["id"]), url)
    return results


def _link(url: str) -> str:
    """An inline markdown citation labelled with the page's host name."""
    host = urlparse(url).hostname or url
    return f"[{host.removeprefix('www.')}]({url})"


def _cite(text: str, results: dict[str, str], sources: list[str]) -> str:
    """Rewrite citation markers as inline links and record each cited URL in order.

    A marker whose id matches no search result is left as written.
    """
    def replace(match: re.Match) -> str:
        urls = [results[i] for i in _MARKER_ID.findall(match.group(0)) if i in results]
        if not urls:
            return match.group(0)
        for url in urls:
            if url not in sources:
                sources.append(url)
        return "(" + ", ".join(_link(u) for u in dict.fromkeys(urls)) + ")"

    return _MARKER_RUN.sub(replace, text)


def _parse_response(data: object) -> dict:
    """Extract the cited answer text and its source URLs from an Agent API payload.

    Raises ResearchError when the payload is not a response object, the run
    failed, or it holds no text — an empty answer is missing evidence, not a
    successful result.
    """
    if not isinstance(data, dict) or not isinstance(data.get("output", []), list):
        raise ResearchError("Perplexity research response was malformed")
    if data.get("status") == "failed":
        raise ResearchError("Perplexity research run failed", retryable=True)
    output = data.get("output", [])
    results = _search_results(output)
    texts: list[str] = []
    sources: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict) or part.get("type") != "output_text":
                continue
            texts.append(_cite(part.get("text") or "", results, sources))
            for ann in part.get("annotations") or []:
                if not isinstance(ann, dict) or ann.get("type") != "url_citation":
                    continue
                url = ann.get("url")
                if isinstance(url, str) and url and url not in sources:
                    sources.append(url)
    summary = "\n".join(texts).strip()
    if not summary:
        raise ResearchError("Perplexity research returned an empty answer")
    return {"summary": summary, "sources": sources, "usage": _usage(data)}


def _usage(data: dict) -> dict:
    """Token counts and USD cost reported by the Agent API (for cost logging); {} when absent."""
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return {}
    out = {k: usage[k] for k in ("input_tokens", "output_tokens", "total_tokens")
           if isinstance(usage.get(k), int)}
    cost = usage.get("cost")
    if isinstance(cost, dict) and isinstance(cost.get("total_cost"), (int, float)):
        out["cost_usd"] = cost["total_cost"]
    return out


def _to_research_error(exc: BaseException) -> ResearchError:
    """Translate a final HTTP/network failure into a sanitized ResearchError."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return ResearchError(f"Perplexity research request failed (HTTP {code})",
                             retryable=_is_retryable(exc))
    return ResearchError(f"Perplexity research request failed ({type(exc).__name__})",
                         retryable=_is_retryable(exc))


class ContractorResearcher:
    """Researches one contractor per call via the Perplexity Agent API."""

    def __init__(self, api_key: str, preset: str = "fast",
                 max_attempts: int = 4, wait=None):
        self._api_key = api_key
        self._preset = preset
        self._max_attempts = max_attempts
        self._wait = wait or wait_exponential(multiplier=1, min=2, max=20)

    async def research(self, contractor: ContractorRecord) -> dict:
        """Research one contractor. Raises ResearchError when no usable evidence comes back."""
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(_is_retryable),
                stop=stop_after_attempt(self._max_attempts),
                wait=self._wait,
                reraise=True,
            ):
                with attempt:
                    data = await self._post(contractor)
        except ResearchError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise _to_research_error(exc) from exc
        return _parse_response(data)

    async def _post(self, contractor: ContractorRecord) -> object:
        """Make one Agent API call (the preset includes web search); return the JSON body."""
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                _AGENT_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "preset": self._preset,
                    "instructions": _SYSTEM,
                    "input": _build_prompt(contractor),
                    "max_output_tokens": 900,
                },
            )
            response.raise_for_status()
            try:
                return response.json()
            except ValueError as exc:
                raise ResearchError("Perplexity research response was malformed (not JSON)") from exc
