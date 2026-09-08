"""Parser tests against hand-built payloads mirroring the real response shapes.

Fixtures are minimal on purpose. The shapes they encode were confirmed live; what these
tests protect is the mapping into the record contract, not the upstream schema.
"""

from ursula.models import AccessRoute
from ursula.sources import figshare, openalex, primo, vtechworks


def primo_doc(**over):
    doc = {
        "pnx": {
            "control": {"recordid": ["cdi_abc_123"]},
            "display": {
                "title": ["Soil Moisture: Soil Moisture"],
                "creator": ["Doe, Jane", "Roe, Sam"],
                "type": ["article"],
                "creationdate": ["c2021"],
            },
            "addata": {
                "doi": ["https://doi.org/10.1/AB"],
                "abstract": ["An abstract."],
            },
        },
        "delivery": {"availability": ["fulltext"], "almaOpenurl": "https://openurl"},
    }
    doc["pnx"]["display"].update(over.pop("display", {}))
    doc["delivery"].update(over.pop("delivery", {}))
    return doc


def test_primo_maps_pnx_into_the_record_contract():
    (rec,) = primo.parse({"docs": [primo_doc()]}, limit=5)
    assert rec.id == "primo:cdi_abc_123"
    assert rec.title == "Soil Moisture"
    assert rec.authors == ["Doe, Jane", "Roe, Sam"]
    assert rec.year == 2021
    assert rec.doi == "10.1/ab"
    assert rec.cite_uri == "https://openurl"


def test_primo_fulltext_availability_means_licensed_not_readable():
    """`fulltext` means a signed-in VT user can read it. It never means this service can."""
    (rec,) = primo.parse({"docs": [primo_doc()]}, limit=5)
    assert rec.access_route is AccessRoute.LICENSED_HANDOFF
    assert rec.readable is False


def test_primo_open_access_flag_wins_over_availability():
    doc = primo_doc(display={"oa": ["free_for_read"]})
    (rec,) = primo.parse({"docs": [doc]}, limit=5)
    assert rec.access_route is AccessRoute.OA_PDF


def test_primo_no_signal_is_abstract_only_and_limit_is_honoured():
    doc = primo_doc(delivery={"availability": []})
    recs = primo.parse({"docs": [doc, doc, doc]}, limit=2)
    assert len(recs) == 2
    assert recs[0].access_route is AccessRoute.ABSTRACT_ONLY


def dspace_item(bundles):
    return {
        "uuid": "u-1",
        "handle": "10919/999",
        "name": "fallback",
        "metadata": {
            "dc.title": [{"value": "A Thesis"}],
            "dc.contributor.author": [{"value": "Doe, Jane"}],
            "dc.date.issued": [{"value": "2019-05-01"}],
            "dc.type": [{"value": "Dissertation"}],
            "dc.description.abstract": [{"value": "Some abstract."}],
        },
        "_embedded": {"bundles": {"_embedded": {"bundles": bundles}}},
    }


def bundle(name, streams=()):
    return {
        "name": name,
        "_embedded": {"bitstreams": {"_embedded": {"bitstreams": list(streams)}}},
    }


TEXT_STREAM = {
    "sizeBytes": 1234,
    "_links": {"content": {"href": "https://vtechworks.lib.vt.edu/x/content"}},
}


def test_vtechworks_text_bundle_makes_a_record_readable():
    rec = vtechworks.to_record(
        dspace_item([bundle("ORIGINAL"), bundle("TEXT", [TEXT_STREAM])])
    )
    assert rec.id == "vtechworks:u-1"
    assert rec.title == "A Thesis"
    assert rec.type == "thesis"
    assert rec.year == 2019
    assert rec.cite_uri == "https://hdl.handle.net/10919/999"
    assert rec.access_route is AccessRoute.VTECHWORKS_TEXT


def test_vtechworks_without_a_text_bundle_is_abstract_only():
    rec = vtechworks.to_record(dspace_item([bundle("ORIGINAL"), bundle("THUMBNAIL")]))
    assert rec.access_route is AccessRoute.ABSTRACT_ONLY
    assert vtechworks.text_bitstream(dspace_item([bundle("ORIGINAL")])) is None


def test_openalex_rebuilds_the_inverted_abstract():
    work = {
        "id": "https://openalex.org/W42",
        "title": "A Paper",
        "publication_year": 2020,
        "type": "article",
        "doi": "https://doi.org/10.5/XY",
        "open_access": {"is_oa": True, "oa_url": "https://pdf"},
        "primary_location": {"landing_page_url": "https://landing"},
        "authorships": [{"author": {"display_name": "Roe, Sam"}}],
        "abstract_inverted_index": {"Soil": [0], "moisture": [1], "varies": [2]},
    }
    rec = openalex.to_record(work)
    assert rec.id == "openalex:W42"
    assert rec.abstract == "Soil moisture varies"
    assert rec.doi == "10.5/xy"
    assert rec.access_route is AccessRoute.OA_PDF
    assert rec.oa_url == "https://pdf"


def test_openalex_closed_work_is_abstract_only_not_licensed():
    """Only Primo knows what VT licenses, so this is the honest floor."""
    rec = openalex.to_record(
        {"id": "x/W1", "title": "T", "open_access": {"is_oa": False}}
    )
    assert rec.access_route is AccessRoute.ABSTRACT_ONLY


def test_figshare_record_is_readable_only_when_it_has_files():
    article = {
        "id": 31839082,
        "title": "A Dataset",
        "doi": "10.7294/31839082.v1",
        "published_date": "2026-09-03T14:04:11Z",
        "defined_type_name": "dataset",
        "url_public_html": "https://data.lib.vt.edu/x",
        "description": "Notes.",
        "authors": [{"full_name": "Doe, Jane"}],
        "files": [{"name": "readme.txt", "download_url": "https://dl"}],
    }
    rec = figshare.to_record(article)
    assert rec.id == "figshare:31839082"
    assert rec.source == "vtdr"
    assert rec.access_route is AccessRoute.FIGSHARE_FILE
    assert (
        figshare.to_record({**article, "files": []}).access_route
        is AccessRoute.ABSTRACT_ONLY
    )
