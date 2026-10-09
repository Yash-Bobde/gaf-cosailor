"""Adversarial tests for decision-maker / contact grounding (enricher.ground_decision_makers).

The model proposes people; deterministic code decides what a rep may see:
  * a full name (≥ 2 real name words) that appears as whole words in the research
  * a title only when the research supports it near that name — otherwise "unknown"
  * a source URL only when it is one of the citations the search tool returned
  * role 'decision_maker' only when the supported title shows leadership/purchasing
    authority; everyone else is a 'contact'
"""
import pytest

from app.services.enricher import ground_decision_makers

_SOURCES = ["https://acme.example/about", "https://bbb.org/acme"]


def _ground(candidates, summary, sources=_SOURCES):
    return ground_decision_makers(candidates, {"summary": summary, "sources": sources})


def _person(name, title=None, url=None):
    return {"name": name, "title": title, "source_url": url}


@pytest.mark.parametrize("name", ["J. Smith", "J Smith", "John S.", "JS", "M. L.", "Smith"])
def test_initials_and_single_names_are_rejected(name):
    summary = "Owner J. Smith (John S., JS, M. L. Smith) runs the company."
    assert _ground([_person(name, "Owner")], summary) == []


def test_name_not_in_research_is_rejected():
    assert _ground([_person("John Hallucinated", "CEO")], "Acme is run by Maria Lopez.") == []


def test_name_must_match_whole_words_not_substrings():
    """'Ann Lee' must not ground against 'Joann Leeds'."""
    assert _ground([_person("Ann Lee", "Owner")], "Founder Joann Leeds started Acme.") == []


def test_generic_role_phrases_are_not_people():
    summary = "The Owner Operator answers calls. Contact the Sales Team."
    assert _ground([_person("Owner Operator"), _person("Sales Team")], summary) == []


def test_supported_owner_is_a_decision_maker_with_evidence_and_citation():
    summary = "Acme Roofing was founded in 1998. Owner Maria Lopez oversees all bids."
    [p] = _ground([_person("Maria Lopez", "Owner", "https://bbb.org/acme")], summary)
    assert p.role == "decision_maker"
    assert p.title == "Owner"
    assert p.source_url == "https://bbb.org/acme"
    assert "Maria Lopez" in p.evidence


def test_unsupported_title_becomes_unknown_and_person_is_only_a_contact():
    summary = "Dev Patel answered our questions about scheduling."
    [p] = _ground([_person("Dev Patel", "President")], summary)
    assert p.title is None
    assert p.role == "contact"


def test_title_supported_only_for_a_different_person_is_not_borrowed():
    summary = "Maria Lopez is the president. Separately, Dev Patel handles warranty paperwork."
    people = _ground([_person("Dev Patel", "President")], summary)
    assert [(p.name, p.title, p.role) for p in people] == [("Dev Patel", None, "contact")]


def test_non_authority_title_is_a_contact():
    summary = "Sales representative Kim Nguyen handles residential estimates."
    [p] = _ground([_person("Kim Nguyen", "Sales Representative")], summary)
    assert (p.title, p.role) == ("Sales Representative", "contact")


@pytest.mark.parametrize("title", ["Purchasing Manager", "Director of Operations",
                                   "Co-Founder", "Vice President", "General Manager"])
def test_leadership_and_purchasing_titles_are_decision_makers(title):
    summary = f"Pat Rivera, {title} at Acme, approves supplier accounts."
    [p] = _ground([_person("Pat Rivera", title)], summary)
    assert p.role == "decision_maker"


def test_uncited_source_url_is_dropped_but_supported_person_is_kept():
    summary = "Owner Maria Lopez founded Acme."
    [p] = _ground([_person("Maria Lopez", "Owner", "https://made-up.example/team")], summary)
    assert p.source_url is None


def test_no_decision_makers_found_returns_empty_list():
    assert _ground([], "No named people were found for this contractor.") == []
    assert _ground("none", "Owner Maria Lopez.") == []
    assert _ground([_person(None), "Maria Lopez", 42], "Owner Maria Lopez.") == []


def test_duplicates_are_collapsed_and_list_is_capped():
    names = ["Ann Adams", "Ben Brown", "Cal Clark", "Dee Dunn", "Eve Evans", "Fay Fox"]
    summary = " ".join(f"Owner {n}." for n in names)
    people = _ground([_person("ann adams", "Owner"), *[_person(n, "Owner") for n in names]], summary)
    assert [p.name for p in people] == ["ann adams", "Ben Brown", "Cal Clark", "Dee Dunn", "Eve Evans"]


def test_evidence_is_truncated_to_a_short_excerpt():
    summary = "Owner Maria Lopez " + "leads a very busy crew " * 40 + "."
    [p] = _ground([_person("Maria Lopez", "Owner")], summary)
    assert len(p.evidence) <= 240


def test_evidence_is_plain_text_without_markdown_or_citation_links():
    """Research text carries inline citation links and markdown; the quote must not."""
    summary = ("1. **Reputation:** A+ at BBB. ([bbb.org](https://www.bbb.org/us/nj/totowa/profile/"
               "construction-services/acme-0221-90163532))\n"
               "5. **Decision-makers:** BBB lists **Maria Lopez, Owner** "
               "([bbb.org](https://bbb.org/acme), [acme.example](https://acme.example/about)).")
    [person] = _ground([_person("Maria Lopez", "Owner", "https://bbb.org/acme")], summary)

    assert person.evidence == "Decision-makers: BBB lists Maria Lopez, Owner."
    assert person.title == "Owner" and person.role == "decision_maker"
    assert person.source_url == "https://bbb.org/acme"
