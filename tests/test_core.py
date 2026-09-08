from ursula.core import merge
from ursula.models import AccessRoute, Record


def rec(source, route, **kw):
    return Record(
        id=f"{source}:{kw.pop('n', 1)}",
        title=kw.pop("title", "A Paper"),
        source=source,
        access_route=route,
        **kw,
    )


def test_merge_on_doi_keeps_the_route_that_yields_text():
    """The published-vs-deposited pattern: cite the article, read the VT copy."""
    published = rec("openalex", AccessRoute.ABSTRACT_ONLY, doi="10.1/x", year=2021)
    deposited = rec("vtechworks", AccessRoute.VTECHWORKS_TEXT, doi="10.1/x")
    (merged,) = merge([[published], [deposited]])
    assert merged.source == "vtechworks"
    assert merged.access_route is AccessRoute.VTECHWORKS_TEXT
    assert merged.also_in == ["openalex"]
    assert merged.year == 2021, "richer metadata survives the merge"


def test_merge_fills_gaps_from_the_discarded_side():
    a = rec("vtechworks", AccessRoute.VTECHWORKS_TEXT, doi="10.1/x")
    b = rec(
        "primo",
        AccessRoute.LICENSED_HANDOFF,
        doi="10.1/x",
        abstract="Abstract.",
        cite_uri="https://openurl",
        authors=["Doe, Jane"],
    )
    (merged,) = merge([[a], [b]])
    assert merged.abstract == "Abstract."
    assert merged.cite_uri == "https://openurl"
    assert merged.authors == ["Doe, Jane"]


def test_merge_matches_on_title_and_year_without_a_doi():
    a = rec("primo", AccessRoute.LICENSED_HANDOFF, title="The Soil Study", year=2020)
    b = rec("vtechworks", AccessRoute.VTECHWORKS_TEXT, title="Soil Study", year=2020)
    assert len(merge([[a], [b]])) == 1


def test_merge_keeps_genuinely_different_works_apart():
    a = rec("primo", AccessRoute.OA_PDF, title="Soil Study", year=2020)
    b = rec("primo", AccessRoute.OA_PDF, title="Water Study", year=2020, n=2)
    assert len(merge([[a], [b]])) == 2


def test_merge_sorts_readable_records_first():
    handoff = rec("primo", AccessRoute.LICENSED_HANDOFF, title="B", rank=0)
    readable = rec("vtechworks", AccessRoute.VTECHWORKS_TEXT, title="A", rank=4)
    order = [r.access_route for r in merge([[handoff], [readable]])]
    assert order == [AccessRoute.VTECHWORKS_TEXT, AccessRoute.LICENSED_HANDOFF]
