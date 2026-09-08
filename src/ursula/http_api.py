"""HTTP face — for NebulaONE and VT's Open WebUI.

Every operation is a GET with flat query parameters, because NebulaONE can register
`?param=value` URLs and nothing else. That restriction is not a tax; it forces the
lowest common denominator every host can call, which is exactly the shape a
provider-agnostic API wants anyway.

Open WebUI imports the OpenAPI document at /openapi.json directly as a tool server.

    uvicorn ursula.http_api:app --port 8000
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, HTTPException, Query

from . import core
from .config import MAILTO

app = FastAPI(
    title="Ursula",
    version="0.1.0",
    summary="Library research over Virginia Tech's discovery, repository and open-access sources.",
    description=(
        "Searches Primo VE, VTechWorks, the VT Data Repository and OpenAlex, normalizes "
        "them to one record shape, and returns ranked passages rather than whole "
        "documents. Every record carries an `access_route` saying whether its text can "
        "actually be read; never state or imply you have read something whose route is "
        "`abstract_only` or `licensed_handoff`."
    ),
)

Q = Annotated[
    str,
    Query(
        description=(
            "The research topic, as plain keywords — for example 'machine learning soil "
            "moisture'. Three to six substantive nouns works best. Strip question "
            "phrasing such as 'how does' or 'what is', and do not use boolean operators; "
            "the upstream indexes treat them as literal search terms."
        ),
        min_length=2,
        max_length=400,
    ),
]

SOURCES = Annotated[
    str,
    Query(
        description=(
            "Comma-separated sources. `primo` is the library's discovery layer and has "
            "by far the broadest coverage, but you will rarely be able to read what it "
            "finds. `vtechworks` is VT's institutional repository and the only source "
            "whose full text is readable. `openalex` finds legal open copies of "
            "paywalled work. `vtdr` is VT's data repository, for datasets rather than "
            "prose. `primo_catalog` is VT's own books and physical holdings. "
            "Default searches primo, vtechworks and openalex together."
        ),
        pattern=r"^[a-z_,\s]*$",  # empty is the documented default
    ),
]


def _sources(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return core.DEFAULT_SOURCES
    chosen = tuple(s.strip() for s in raw.split(",") if s.strip())
    unknown = [s for s in chosen if s not in core.SOURCES]
    if unknown:
        raise HTTPException(
            400, f"unknown source(s) {unknown}; valid: {', '.join(core.SOURCES)}"
        )
    return chosen or core.DEFAULT_SOURCES


@app.get("/health", summary="Liveness and configuration check")
async def health() -> dict:
    return {"ok": True, "version": "0.1.0", "mailto_configured": bool(MAILTO)}


@app.get("/search", summary="Search VT's library sources and return merged records")
async def search_endpoint(
    query: Q,
    sources: SOURCES = "",
    limit: Annotated[int, Query(ge=1, le=20, description="Results per source.")] = 5,
    readable_only: Annotated[
        bool,
        Query(description="Keep only records whose full text this service can fetch."),
    ] = False,
) -> dict:
    return await core.search(query, _sources(sources), limit, readable_only)


@app.get("/read", summary="Read a record's full text, reduced to relevant passages")
async def read_endpoint(
    id: Annotated[
        str,
        Query(
            description=(
                "A record `id` exactly as returned by /search, such as "
                "`vtechworks:2f0e…`. Only records with `readable: true` have text."
            )
        ),
    ],
    question: Annotated[
        str,
        Query(
            description=(
                "What you want to learn from the document, in the user's own terms. "
                "Passages are ranked against this, so a specific question returns a far "
                "better excerpt than a topic. Omit it to get the document's opening."
            )
        ),
    ] = "",
    max_chars: Annotated[
        int, Query(ge=200, le=40000, description="Ceiling on returned text.")
    ] = 6000,
) -> dict:
    return await core.read(id, question, max_chars)


@app.get("/resolve", summary="Look up a DOI's open-access status")
async def resolve_endpoint(
    doi: Annotated[
        str,
        Query(
            description=(
                "A DOI, bare or as a full doi.org URL — both are accepted. Returns "
                "`oa_url` when a legal open copy exists."
            )
        ),
    ],
) -> dict:
    return await core.resolve(doi)
