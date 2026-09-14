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
        "documents. Results are ordered by relevance, not by what can be read: a "
        "paywalled article is often the best answer, and every record carries an "
        "`access_route` and a link saying how to get at it. Never state or imply you "
        "have read something whose route is `abstract_only` or `licensed_handoff`."
    )
)

# Endpoint descriptions, shared with agent/endpoints.md. NebulaONE caps one at 1024
# characters, so these say what a model needs before deciding to call: what the endpoint
# covers, how results are ordered, what comes back. Parameter-specific detail goes in the
# Query() descriptions below, where no such cap applies.
MAX_DESCRIPTION_CHARS = 1024

SEARCH_DESCRIPTION = "Search Virginia Tech's library sources — the Primo discovery layer, the VTechWorks institutional repository, the VT Data Repository and OpenAlex — and return the few most relevant records, merged and deduplicated. If the request is broad, ask the user to narrow it before calling.\n\nResults are ordered by relevance and interleaved across sources. Access route is a tiebreak, never a ranking: a paywalled article the sources ranked first still comes first, because a VT user reaches it by signing in.\n\nEvery record carries access_route (vtechworks_text, figshare_file, oa_pdf, abstract_only or licensed_handoff), readable, a cite_uri for sending a human, and oa_url where a legal open copy exists. also_in lists other sources holding the same work, usually VT's deposited manuscript of a paywalled article. matched and more_available say how many relevant results were left out: offer those to the user rather than fetching them unasked. notes carries anything worth saying out loud, such as a source that failed."

READ_DESCRIPTION = "Return a document's full text, reduced to the passages that answer a question. Call it only on records marked readable; anything else comes back with guidance on what to do instead, not an error.\n\nPassages arrive in document order, with chars_total and chars_returned so you know how much you did not see. You are reading an excerpt, not the document: when the passages do not settle the question, say what you saw rather than implying you read the whole thing. Reading several documents in one conversation is expected."

RESOLVE_DESCRIPTION = "Turn a DOI into open-access status, backed by OpenAlex. Returns oa_url when a legal open copy exists. Call it on anything the discovery layer surfaced behind a subscription, before telling someone they cannot read it."

for _d in (SEARCH_DESCRIPTION, READ_DESCRIPTION, RESOLVE_DESCRIPTION):
    assert len(_d) <= MAX_DESCRIPTION_CHARS, (
        "endpoint description exceeds the platform cap"
    )


# Parameter descriptions, shared with agent/endpoints.md. No cap applies to these, so
# the parameter-specific detail lives here rather than in the endpoint description.
QUERY_DESCRIPTION = "The research topic to search for, as plain keywords — for example 'machine learning soil moisture'. Do not use boolean operators, quotation marks, or field prefixes; the upstream indexes treat them as literal search terms. Three to six substantive nouns works best. Full sentences and question phrasing reduce recall sharply, so strip words like 'how does' and 'what is' before calling."

SOURCES_DESCRIPTION = "Comma-separated list of sources to search, or omit for the default of primo, vtechworks and openalex together. 'primo' is the library's discovery layer and has by far the broadest coverage, but you will rarely be able to read what it finds. 'vtechworks' is VT's institutional repository and the only source whose full text can actually be read, so include it whenever reading the document matters. 'openalex' finds legal open-access copies of paywalled work. 'vtdr' is VT's data repository, for datasets rather than prose. 'primo_catalog' is VT's own books and physical holdings, for 'does the library have X'."

LIMIT_DESCRIPTION = "How deep to search each source before merging, between 1 and 20. Five is the default and is usually right. This is not how many results come back — max_results decides that — so raising it only helps when the right record might sit below the top five of a single source."

MAX_RESULTS_DESCRIPTION = "How many of the merged, relevance-ordered records to return, between 1 and 20. The default of 5 is the right answer size for almost every question, and every extra record costs context you will want later for reading. Raise it only when the user asks for more or a literature review genuinely needs breadth. If the top five are off-target, refine the query instead of asking for more."

READABLE_ONLY_DESCRIPTION = "Discard every record whose full text cannot be fetched. False by default and rarely what you want, because it drops the licensed and catalog material that is often the most relevant answer, leaving only what happens to be open. Set it true only when the task genuinely requires reading text, such as comparing the methods sections of several papers."

ID_DESCRIPTION = "A record id exactly as it appeared in a /search response, such as 'vtechworks:b716bd09-0c7b-4c06-b582-4301b27cf5fe'. Only records marked 'readable': true have retrievable text; calling this on anything else returns guidance on what to do instead, not an error."

QUESTION_DESCRIPTION = "What you want to learn from this document, phrased in the user's own terms — for example 'what accuracy did the model achieve and on what data'. Passages are ranked against this, so a specific question returns a far better excerpt than a bare topic. Omit it and you get the document's opening instead, which is rarely what you want."

MAX_CHARS_DESCRIPTION = "Ceiling on the characters of document text returned, between 200 and 40000. The default of 6000 is a few pages and answers most questions. Raise it for a synthesis across a whole argument; lower it when reading several documents in one conversation."

DOI_DESCRIPTION = "A DOI, either bare like '10.1007/s11269-024-04069-3' or as a full 'https://doi.org/...' URL — both are accepted, so no stripping is needed. Call this on anything the discovery layer surfaced behind a subscription, before telling the user they cannot read it. Returns 'oa_url' when a legal open copy exists."

Q = Annotated[str, Query(description=QUERY_DESCRIPTION, min_length=2, max_length=400)]

SOURCES = Annotated[
    str,
    # Empty is the documented default.
    Query(description=SOURCES_DESCRIPTION, pattern=r"^[a-z_,\s]*$"),
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


@app.get(
    "/search",
    summary="Search VT's library sources and return merged records",
    description=SEARCH_DESCRIPTION,
)
async def search_endpoint(
    query: Q,
    sources: SOURCES = "",
    limit: Annotated[int, Query(ge=1, le=20, description=LIMIT_DESCRIPTION)] = 5,
    readable_only: Annotated[
        bool, Query(description=READABLE_ONLY_DESCRIPTION)
    ] = False,
    max_results: Annotated[
        int, Query(ge=1, le=20, description=MAX_RESULTS_DESCRIPTION)
    ] = 5,
) -> dict:
    return await core.search(
        query, _sources(sources), limit, readable_only, max_results=max_results
    )


@app.get(
    "/read",
    summary="Read a record's full text, reduced to relevant passages",
    description=READ_DESCRIPTION,
)
async def read_endpoint(
    id: Annotated[str, Query(description=ID_DESCRIPTION)],
    question: Annotated[str, Query(description=QUESTION_DESCRIPTION)] = "",
    max_chars: Annotated[
        int, Query(ge=200, le=40000, description=MAX_CHARS_DESCRIPTION)
    ] = 6000,
) -> dict:
    return await core.read(id, question, max_chars)


@app.get(
    "/resolve",
    summary="Look up a DOI's open-access status",
    description=RESOLVE_DESCRIPTION,
)
async def resolve_endpoint(
    doi: Annotated[str, Query(description=DOI_DESCRIPTION)],
) -> dict:
    return await core.resolve(doi)
