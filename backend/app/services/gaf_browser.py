"""Headless-browser half of the GAF scraper: load the locator page once.

GAF's contractor locator is a React SPA behind Akamai Bot Manager. Its own
JavaScript calls a Coveo search API; we load the page in headless Chromium
(with a small stealth init script) and capture that first Coveo exchange:
the auth token, the request body (which carries the geocoded search origin),
the first batch of results, and the session cookies. Everything after that
is plain HTTP — see playwright_scraper._paginate_coveo.
"""
import json
import logging
from dataclasses import dataclass, field

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.services.errors import ScrapeError

logger = logging.getLogger(__name__)

COVEO_URL_FRAGMENT = "coveo.com/rest/search"

# React + the Akamai challenge can take 10-20 s on slow hosts.
_COVEO_TIMEOUT_MS = 45_000
_PAGE_TIMEOUT_MS = 60_000

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
SEC_CH_UA = '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"'

_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled", "--no-sandbox",
    "--disable-dev-shm-usage", "--disable-gpu", "--no-zygote",
    "--disable-setuid-sandbox", "--single-process", "--disable-extensions",
    "--disable-software-rasterizer", "--window-size=1280,800",
]

_CONTEXT_OPTIONS = {
    "user_agent": USER_AGENT,
    "viewport": {"width": 1280, "height": 800},
    "locale": "en-US",
    "timezone_id": "America/New_York",
    "extra_http_headers": {
        "Accept-Language": "en-US,en;q=0.9",
        "sec-ch-ua": SEC_CH_UA,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    },
}

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true });
if (!window.chrome) {
    window.chrome = { app: { isInstalled: false }, runtime: {}, loadTimes: function() {}, csi: function() {} };
}
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const arr = [
            { name: 'Chrome PDF Plugin',   filename: 'internal-pdf-viewer',            description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer',   filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client',       filename: 'internal-nacl-plugin',            description: '' },
        ];
        arr.item = (i) => arr[i];
        arr.namedItem = (n) => arr.find(p => p.name === n) || null;
        arr.refresh = () => {};
        return arr;
    },
    configurable: true,
});
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'], configurable: true });
const _origPermQuery = window.navigator.permissions && window.navigator.permissions.query;
if (_origPermQuery) {
    window.navigator.permissions.query = (params) =>
        params.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : _origPermQuery.call(navigator.permissions, params);
}
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8, configurable: true });
['__cdc_asdjflasutopfhvcZLmcfl_Array','__cdc_asdjflasutopfhvcZLmcfl_Promise','__cdc_asdjflasutopfhvcZLmcfl_Symbol'].forEach(k => {
    try { delete window[k]; } catch(_) {}
});
"""


@dataclass(frozen=True)
class FirstPage:
    """Everything captured from the browser's first Coveo exchange."""
    results: list[dict] = field(default_factory=list)
    total_count: int = 0
    token: str = ""
    request_body: dict = field(default_factory=dict)
    cookie_header: str = ""


def parse_coveo_payload(data) -> tuple[list[dict], int]:
    """Validate a Coveo search response and return (results, totalCount).

    Raises ScrapeError for anything that is not a well-formed Coveo body —
    an Akamai challenge page, an error JSON or a schema change must fail the
    run, never masquerade as "GAF has no contractors here".
    """
    if not isinstance(data, dict):
        raise ScrapeError("GAF search response was malformed (not a JSON object)")
    results, total = data.get("results"), data.get("totalCount")
    if not isinstance(results, list) or isinstance(total, bool) or not isinstance(total, int):
        raise ScrapeError("GAF search response was malformed (missing results/totalCount)")
    if total < 0 or not all(isinstance(r, dict) for r in results):
        raise ScrapeError("GAF search response was malformed (invalid result entries)")
    return results, total


async def capture_first_page(url: str) -> FirstPage:
    """Load the GAF locator in headless Chromium and capture the first Coveo response.

    Raises ScrapeError when the browser cannot launch, the page or its Coveo
    call does not load, or the response is malformed. A valid response with
    totalCount=0 is returned normally — that is a genuine empty territory.
    """
    captured: dict = {}

    def on_request(req) -> None:
        if COVEO_URL_FRAGMENT in req.url and "token" not in captured:
            captured["token"] = req.headers.get("authorization", "")
            try:
                captured["body"] = json.loads(req.post_data or "{}")
            except ValueError:
                captured["body"] = {}

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=_LAUNCH_ARGS)
            try:
                data, cookies = await _capture_raw(browser, url, on_request)
            finally:
                await browser.close()
    except ScrapeError:
        raise
    except PlaywrightTimeoutError as exc:
        raise ScrapeError("GAF locator did not return search results in time "
                          "(page timeout or bot challenge)", retryable=True) from exc
    except Exception as exc:
        logger.warning("Playwright phase failed for %s: %s", url, type(exc).__name__)
        raise ScrapeError(f"GAF locator page could not be loaded ({type(exc).__name__})",
                          retryable=True) from exc

    results, total = parse_coveo_payload(data)
    logger.info("Coveo first batch: %d results, totalCount=%d", len(results), total)
    return FirstPage(
        results=results,
        total_count=total,
        token=captured.get("token", ""),
        request_body=captured.get("body", {}),
        cookie_header="; ".join(f"{c['name']}={c['value']}" for c in cookies),
    )


async def _capture_raw(browser, url: str, on_request) -> tuple[object, list[dict]]:
    """Open one page, wait for GAF's own Coveo call; return (json body, cookies)."""
    context = await browser.new_context(**_CONTEXT_OPTIONS)
    await context.add_init_script(STEALTH_JS)
    page = await context.new_page()
    page.on("request", on_request)

    # expect_response keeps a reference to the Coveo response until its body is
    # read; an async on_response callback races the browser freeing the buffer.
    async with page.expect_response(
        lambda r: COVEO_URL_FRAGMENT in r.url, timeout=_COVEO_TIMEOUT_MS,
    ) as resp_info:
        await page.goto(url, wait_until="domcontentloaded", timeout=_PAGE_TIMEOUT_MS)
    coveo_resp = await resp_info.value
    if not coveo_resp.ok:
        raise ScrapeError(f"GAF search API answered HTTP {coveo_resp.status}", retryable=True)
    try:
        data = await coveo_resp.json()
    except ValueError as exc:
        raise ScrapeError("GAF search response was malformed (not JSON)") from exc
    return data, await context.cookies()
