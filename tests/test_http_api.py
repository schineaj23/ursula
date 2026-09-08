"""The shim's contract, checked without touching the network.

The thing worth protecting here is that every operation stays a GET with flat query
parameters. NebulaONE can register that form and nothing else.
"""

import pytest
from fastapi.testclient import TestClient

from ursula import core, http_api


@pytest.fixture
def app(monkeypatch):
    async def fake_search(
        query, sources, limit, readable_only=False, abstract_chars=500
    ):
        return {
            "query": query,
            "sources": list(sources),
            "limit": limit,
            "count": 0,
            "records": [],
        }

    async def fake_read(record_id, question="", max_chars=6000):
        return {"id": record_id, "question": question, "max_chars": max_chars}

    async def fake_resolve(doi):
        return {"doi": doi}

    monkeypatch.setattr(core, "search", fake_search)
    monkeypatch.setattr(core, "read", fake_read)
    monkeypatch.setattr(core, "resolve", fake_resolve)
    return TestClient(http_api.app)


def test_every_route_is_a_get_with_query_parameters_only():
    for path, item in http_api.app.openapi()["paths"].items():
        assert set(item) == {"get"}, f"{path} must be GET-only for NebulaONE"
        for param in item["get"].get("parameters", []):
            assert param["in"] == "query", f"{path} has a non-query parameter"


def test_search_defaults_to_the_three_core_sources(app):
    body = app.get("/search", params={"query": "soil"}).json()
    assert body["sources"] == list(core.DEFAULT_SOURCES)


def test_search_accepts_a_comma_separated_subset(app):
    body = app.get(
        "/search", params={"query": "soil", "sources": "vtechworks, openalex"}
    ).json()
    assert body["sources"] == ["vtechworks", "openalex"]


def test_search_rejects_an_unknown_source_by_name(app):
    resp = app.get("/search", params={"query": "soil", "sources": "scopus"})
    assert resp.status_code in (400, 422)


def test_search_bounds_the_limit(app):
    assert app.get("/search", params={"query": "soil", "limit": 99}).status_code == 422


def test_read_passes_the_question_through(app):
    body = app.get(
        "/read", params={"id": "vtechworks:u1", "question": "what accuracy"}
    ).json()
    assert body == {
        "id": "vtechworks:u1",
        "question": "what accuracy",
        "max_chars": 6000,
    }


def test_health_reports_configuration(app):
    assert app.get("/health").json()["ok"] is True
