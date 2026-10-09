"""Deterministic grounding of model-proposed people against the web research.

The enrichment model proposes decision-makers; this module decides what a rep
is allowed to see. A person survives only when:

  * the name is a meaningful full name — at least two real name words, no
    initials, no generic role phrases ("Owner Operator", "Sales Team");
  * that full name appears as whole words in the research text;

and then:

  * the title is kept only if the research supports it in the same sentence,
    close to the name — otherwise it becomes unknown (None);
  * role is 'decision_maker' only when that SUPPORTED title shows leadership or
    purchasing authority; everyone else is a 'contact';
  * source_url is kept only if it is one of the citations the search tool
    actually returned;
  * evidence is the research sentence that mentions the person, as plain text:
    markdown, citation links and bare URLs are stripped (the source link is
    shown separately), so a quote never carries raw markup or a long URL.

Limitation (documented, not hidden): this proves the research text names the
person with that title. It does not prove the cited page says so, that the
person still works there, or that they sign purchase orders.
"""
import re

from app.models.lead import DecisionMaker

MAX_PEOPLE = 5
_EVIDENCE_MAX = 240
_TITLE_WINDOW = 60   # max characters between a title mention and the name

_NAME_WORD = re.compile(r"^[A-Za-z][A-Za-z'’-]*[A-Za-z]$")
_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}
_GENERIC_WORDS = {
    "owner", "operator", "team", "sales", "office", "staff", "customer", "service",
    "services", "department", "support", "company", "roofing", "contact", "info",
    "manager", "management", "admin", "the", "crew", "estimator", "unknown", "n/a",
}
_TITLE_STOPWORDS = {"of", "the", "and", "at", "&", "for", "a"}
_AUTHORITY = re.compile(
    r"\b(owner|co-?owner|proprietor|founder|co-?founder|president|ceo|coo|cfo|chief|"
    r"principal|partner|general manager|managing director|purchasing|procurement|buyer|"
    r"operations manager|operations director|director of operations|head of operations)\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")

# Markdown in the research text, removed before matching names and quoting evidence.
_MD_LINK = r"\[[^\]]*\]\([^)\s]*\)"
_CITATION_GROUP = re.compile(rf"\s*\(\s*{_MD_LINK}(?:\s*,\s*{_MD_LINK})*\s*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)\s]*\)")
_BARE_URL = re.compile(r"<?https?://[^\s)>]+>?")
_LINE_PREFIX = re.compile(r"(?m)^[ \t]*(?:#{1,6}[ \t]+|[-+•][ \t]+|\d+[.)][ \t]+)")
_EMPHASIS = re.compile(r"\*+|__")


def _name_words(name: str) -> list[str] | None:
    """Return the name's words if it is a meaningful full name, else None."""
    words = [w.strip(",") for w in name.split()]
    core = [w for w in words if w.lower() not in _SUFFIXES]
    if not 2 <= len(core) <= 5:
        return None
    if not all(_NAME_WORD.match(w) for w in core):
        return None
    if any(w.lower() in _GENERIC_WORDS for w in core):
        return None
    return core


def _name_pattern(words: list[str]) -> re.Pattern:
    body = r"\s+".join(re.escape(w) for w in words)
    return re.compile(rf"(?<![A-Za-z]){body}(?![A-Za-z])", re.IGNORECASE)


def _title_pattern(title: str) -> re.Pattern | None:
    words = [w for w in re.split(r"[\s,/]+", title.lower()) if w and w not in _TITLE_STOPWORDS]
    if not words:
        return None
    parts = [re.escape(w).replace(r"\-", r"[-\s]?") for w in words]
    return re.compile(r"(?<![a-z])" + r"(?:\W+(?:\w+\W+){0,2}?)".join(parts) + r"(?![a-z])",
                      re.IGNORECASE)


def _plain(text: str) -> str:
    """Research markdown as plain text: no citation links, URLs, emphasis or list markers."""
    text = _CITATION_GROUP.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _BARE_URL.sub("", text)
    text = _LINE_PREFIX.sub("", text)
    text = _EMPHASIS.sub("", text)
    text = re.sub(r"[ \t]+([.,;:])", r"\1", text)
    text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)   # "Pres. (link)." -> "Pres." (keeps "...")
    return re.sub(r"[ \t]{2,}", " ", text)


def _evidence_sentence(summary: str, pattern: re.Pattern) -> str | None:
    for sentence in _SENTENCE_SPLIT.split(summary):
        if pattern.search(sentence):
            return sentence.strip()
    return None


def _title_supported(sentence: str, name_pat: re.Pattern, title: str) -> bool:
    title_pat = _title_pattern(title)
    name_match = name_pat.search(sentence)
    if not title_pat or not name_match:
        return False
    for t in title_pat.finditer(sentence):
        gap = max(name_match.start() - t.end(), t.start() - name_match.end())
        if gap <= _TITLE_WINDOW:
            return True
    return False


def _clip(text: str) -> str:
    return text if len(text) <= _EVIDENCE_MAX else text[: _EVIDENCE_MAX - 1].rstrip() + "…"


def _ground_one(item, summary: str, sources: set[str]) -> DecisionMaker | None:
    """Apply every rule to one model-proposed person; None when it must be dropped."""
    if not isinstance(item, dict) or not isinstance(item.get("name"), str):
        return None
    name = " ".join(item["name"].split())
    words = _name_words(name)
    if not words:
        return None
    name_pat = _name_pattern(words)
    sentence = _evidence_sentence(summary, name_pat)
    if not sentence:
        return None
    raw_title = item.get("title") if isinstance(item.get("title"), str) else ""
    title = raw_title.strip()[:120] or None
    if title and not _title_supported(sentence, name_pat, title):
        title = None
    url = item.get("source_url")
    return DecisionMaker(
        name=name[:120],
        title=title,
        source_url=url if isinstance(url, str) and url in sources else None,
        role="decision_maker" if title and _AUTHORITY.search(title) else "contact",
        evidence=_clip(sentence),
    )


def ground_decision_makers(candidates, research: dict) -> list[DecisionMaker]:
    """Keep only people the research supports; downgrade unsupported titles to unknown."""
    if not isinstance(candidates, list):
        return []
    summary = _plain(research.get("summary") or "")
    sources = set(research.get("sources") or [])
    grounded: list[DecisionMaker] = []
    seen: set[str] = set()
    for item in candidates:
        person = _ground_one(item, summary, sources)
        if person is None or person.name.lower() in seen:
            continue
        seen.add(person.name.lower())
        grounded.append(person)
    return grounded[:MAX_PEOPLE]
