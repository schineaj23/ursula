import pytest

from ursula import core
from ursula.core import client
from ursula.models import AccessRoute
from ursula.sources import figshare, openalex, primo, vtechworks

pytestmark = pytest.mark.live

QUERY = "machine learning soil moisture"


@pytest.fixture
async def http():
    async with client() as c:
        yield c


async def test_primo_returns_records_with_handoff_links(http):
    records = await primo.search(http, QUERY, limit=5)
    assert len(records) == 5
    assert all(r.title and r.id.startswith("primo:") for r in records)
    assert any(r.cite_uri for r in records), "almaOpenurl is the handoff path"


async def test_primo_catalog_scope_returns_books(http):
    records = await primo.search(http, "soil physics", limit=3, catalog=True)
    assert records and any(r.type == "book" for r in records)


async def test_vtechworks_search_reports_readability_without_extra_hops(http):
    records = await vtechworks.search(http, QUERY, limit=5)
    assert len(records) == 5
    assert any(r.access_route is AccessRoute.VTECHWORKS_TEXT for r in records)


async def test_vtechworks_full_text_is_clean_plain_text(http):
    records = await vtechworks.search(http, QUERY, limit=5)
    readable = next(r for r in records if r.readable)
    _, text = await vtechworks.fetch_text(http, readable.id.split(":", 1)[1])
    assert text and len(text) > 5000
    assert "%PDF" not in text[:200], "the TEXT bundle is extracted, not the PDF"


async def test_openalex_select_returns_a_rebuildable_abstract(http):
    records = await openalex.search(http, QUERY, limit=5)
    assert len(records) == 5
    assert any(r.abstract for r in records)


async def test_openalex_resolves_a_doi_as_a_query_parameter(http):
    """This is why Unpaywall is not a dependency: same fact, one call, no path segment."""
    record = await openalex.by_doi(http, "10.1007/s11269-024-04069-3")
    assert record and record.oa_url


async def test_figshare_group_filter_is_still_broken(http):
    """Regression guard on survey-corrections.md §1. If this starts passing, revisit."""
    resp = await http.post(
        f"{figshare.FIGSHARE}/articles/search",
        json={"search_for": "soil moisture", "group": 32433, "limit": 5},
    )
    assert resp.json() == [], (
        "group filter now works — the DOI-prefix workaround may be obsolete"
    )


async def test_figshare_search_keeps_only_vt_dois(http):
    records = await figshare.search(http, "Virginia Tech", limit=3)
    assert records and all(r.doi.startswith("10.7294") for r in records)


async def test_search_merges_sources_into_one_small_payload():
    """The whole argument for the service: ~200 KB upstream, ~20 KB out."""
    import json

    result = await core.search(QUERY, ("primo", "vtechworks", "openalex"), limit=5)
    assert result["count"] >= 10
    assert result["readable"] >= 1
    assert len(json.dumps(result)) < 40_000


async def test_read_reduces_a_full_document_to_relevant_passages():
    found = await core.search(QUERY, ("vtechworks",), limit=3, readable_only=True)
    out = await core.read(found["records"][0]["id"], "what accuracy was reported", 3000)
    assert out["text_available"] is True
    assert out["chars_returned"] <= 3000 < out["chars_total"]
    assert out["passages"]


async def test_read_refuses_records_it_cannot_read():
    out = await core.read("primo:anything")
    assert out["text_available"] is False and out["guidance"]


async def test_search_returns_a_mix_of_access_routes():
    """A result set that is all open access has silently narrowed the library."""
    result = await core.search("climate adaptation coastal virginia", limit=5)
    assert len(result["access_mix"]) >= 3, result["access_mix"]
    top = [r["access_route"] for r in result["records"][:6]]
    assert len(set(top)) >= 2, "the head of the list should not be one route"


async def test_every_primo_record_carries_a_whole_usable_link():
    """A link with a space in it autolinks to 126 of its 795 characters and dies."""
    result = await core.search(
        "climate adaptation coastal virginia", ("primo", "primo_catalog"), limit=5
    )
    links = [r.get("cite_uri") for r in result["records"]]
    assert links and all(links), "every discovery record needs somewhere to send a human"
    assert not [u for u in links if " " in u or "<" in u or ">" in u]
    assert all(u.startswith("https://") for u in links)
