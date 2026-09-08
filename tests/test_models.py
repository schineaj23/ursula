from ursula.models import (
    READABILITY,
    AccessRoute,
    Record,
    clamp,
    dedupe_title,
    normalize_doi,
    normalize_type,
    safe_url,
)


def test_dedupe_title_collapses_primo_repetition():
    assert dedupe_title("Soil Physics: Soil Physics") == "Soil Physics"
    assert dedupe_title("Soil Physics - soil physics") == "Soil Physics"
    assert (
        dedupe_title("Soil Physics: An Introduction") == "Soil Physics: An Introduction"
    )


def test_normalize_doi_strips_every_prefix_form():
    for raw in (
        "10.1234/AB",
        "https://doi.org/10.1234/ab",
        "http://dx.doi.org/10.1234/ab",
        "doi:10.1234/ab",
    ):
        assert normalize_doi(raw) == "10.1234/ab"
    assert normalize_doi(None) is None
    assert normalize_doi("  ") is None


def test_normalize_type_maps_to_the_closed_vocabulary():
    assert normalize_type("Dissertation") == "thesis"
    assert normalize_type("journal-article") == "article"
    assert normalize_type("Dataset") == "dataset"
    assert normalize_type(None) == "other"
    assert normalize_type("sculpture") == "other"


def test_clamp_keeps_whole_words_and_marks_the_cut():
    assert clamp("one two three", 100) == "one two three"
    assert clamp("alpha beta gamma", 11).endswith("…")
    assert clamp(None, 10) is None


def test_merge_key_prefers_doi_then_title_and_year():
    a = Record(
        id="x:1",
        title="A Study",
        source="primo",
        access_route=AccessRoute.OA_PDF,
        doi="10.1/x",
    )
    b = Record(
        id="y:2",
        title="The Study, A",
        source="vtechworks",
        access_route=AccessRoute.OA_PDF,
        year=2020,
    )
    c = Record(
        id="z:3",
        title="Study",
        source="openalex",
        access_route=AccessRoute.OA_PDF,
        year=2020,
    )
    assert a.merge_key() == "doi:10.1/x"
    assert b.merge_key() == c.merge_key()


def test_readability_orders_text_above_links_to_text():
    order = sorted(AccessRoute, key=lambda r: -READABILITY[r])
    assert order[0] is AccessRoute.VTECHWORKS_TEXT
    assert order[-1] is AccessRoute.LICENSED_HANDOFF


def test_to_dict_truncates_authors_and_omits_empty_fields():
    rec = Record(
        id="vtechworks:1",
        title="T",
        source="vtechworks",
        access_route=AccessRoute.VTECHWORKS_TEXT,
        authors=[f"A{i}" for i in range(12)],
    )
    d = rec.to_dict()
    assert d["readable"] is True
    assert len(d["authors"]) == 8 and d["authors_truncated"] == 12
    assert "abstract" not in d and "oa_url" not in d


def test_safe_url_encodes_what_breaks_a_chat_client():
    """Primo emits a literal space in ctx_tim, which truncates the link at 126 chars."""
    raw = (
        "https://na07.alma.exlibrisgroup.com/openurl?ctx_tim=2026-09-08 13:36:41&x=<a>"
    )
    out = safe_url(raw)
    assert " " not in out and "<" not in out and ">" not in out
    assert out.endswith("&x=%3Ca%3E")


def test_safe_url_does_not_double_encode():
    assert safe_url("https://x/?a=%20b") == "https://x/?a=%20b"


def test_safe_url_leaves_url_structure_alone():
    url = "https://x/p?a=1&b=2#frag"
    assert safe_url(url) == url
    assert safe_url(None) is None


def test_records_encode_their_links_on_construction():
    """Normalizing in __post_init__ means a new source cannot forget to."""
    rec = Record(
        id="primo:1",
        title="T",
        source="primo",
        access_route=AccessRoute.LICENSED_HANDOFF,
        cite_uri="https://x/openurl?t=2026-09-08 13:36:41",
        oa_url="https://y/a b.pdf",
    )
    assert " " not in rec.cite_uri
    assert " " not in rec.to_dict()["oa_url"]
