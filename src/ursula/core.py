"""The capability layer: search, read, resolve.

Everything above this is transport. The HTTP shim, the MCP server and the CLI are three
faces on these three functions, which is the whole point — the judgment about what VT's
sources mean lives here once, not in each host's configuration screen.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx

from .config import TIMEOUT, USER_AGENT, VT_DOI_PREFIX
from .models import RANK_BONUS, READABILITY, AccessRoute, Record, clamp
from .rank import rank
from .sources import figshare, openalex, primo, vtechworks

SOURCES = ("primo", "primo_catalog", "vtechworks", "openalex", "vtdr")
DEFAULT_SOURCES = ("primo", "vtechworks", "openalex")

FIGSHARE_RECALL_NOTE = (
    "Figshare topical search does not reliably reach VT's corpus. An empty result means "
    "'not found', not 'VT has no such data' — send the user to data.lib.vt.edu to browse."
)

MIN_USABLE_CHARS = 200
"""Below this, a TEXT bundle extracted to nothing — usually a scan with no OCR layer."""

EMPTY_EXTRACTION = (
    "The repository holds an extracted-text file for this item but it is effectively "
    "empty, which normally means a scanned document with no OCR layer. Treat this record "
    "as abstract-only and say so."
)

NOT_READABLE = {
    AccessRoute.OA_PDF: (
        "A legal open-access copy exists but it is a PDF this service does not parse. "
        "Give the user oa_url. Do not describe contents you have not read."
    ),
    AccessRoute.ABSTRACT_ONLY: (
        "No full text is available for this record. You have metadata and, at most, an "
        "abstract. Say so explicitly rather than inferring contents from the title."
    ),
    AccessRoute.LICENSED_HANDOFF: (
        "VT licenses this; this service cannot retrieve it. Hand the user cite_uri, tell "
        "them to sign in through the library, and offer interlibrary loan."
    ),
}


@asynccontextmanager
async def client():
    async with httpx.AsyncClient(
        timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    ) as c:
        yield c


def merge(groups: list[list[Record]]) -> list[Record]:
    """Fold per-source results into one set.

    The same paper appearing in OpenAlex as the published version and in VTechWorks as
    VT's deposited manuscript is not a duplicate to suppress. It is the open copy of a
    closed article, and it is the most valuable pattern in the system, so the merged
    record keeps the richest metadata and the route that actually yields text.

    The set comes back **ordered by relevance**, interleaved across sources. Access route
    is a tiebreak worth at most one position, so a paywalled article the sources ranked
    first still comes first. What a user asked for is the topic, not the licence.
    """
    merged: dict[str, Record] = {}
    for group in groups:
        for rec in group:
            key = rec.merge_key()
            existing = merged.get(key)
            if existing is None:
                merged[key] = rec
                continue
            keep, other = existing, rec
            if READABILITY[rec.access_route] > READABILITY[existing.access_route]:
                keep, other = rec, existing
            keep.abstract = keep.abstract or other.abstract
            keep.doi = keep.doi or other.doi
            keep.year = keep.year or other.year
            keep.oa_url = keep.oa_url or other.oa_url
            keep.cite_uri = keep.cite_uri or other.cite_uri
            if not keep.authors:
                keep.authors = other.authors
            keep.rank = min(keep.rank, other.rank)
            for src in [other.source, *other.also_in]:
                if src != keep.source and src not in keep.also_in:
                    keep.also_in.append(src)
            merged[key] = keep
    out = list(merged.values())
    out.sort(key=lambda r: (r.rank - RANK_BONUS[r.access_route], r.title.lower()))
    return out


async def _gather(c, query: str, sources, limit: int):
    jobs, names = [], []
    for name in sources:
        if name == "primo":
            jobs.append(primo.search(c, query, limit))
        elif name == "primo_catalog":
            jobs.append(primo.search(c, query, limit, catalog=True))
        elif name == "vtechworks":
            jobs.append(vtechworks.search(c, query, limit))
        elif name == "openalex":
            jobs.append(openalex.search(c, query, limit))
        elif name == "vtdr":
            jobs.append(figshare.search(c, query, limit))
        else:
            continue
        names.append(name)
    results = await asyncio.gather(*jobs, return_exceptions=True)
    groups, notes = [], []
    for name, res in zip(names, results):
        if isinstance(res, BaseException):
            notes.append(f"{name} search failed: {type(res).__name__}: {res}")
            continue
        groups.append(res)
        if name == "vtdr" and not res:
            notes.append(FIGSHARE_RECALL_NOTE)
    return groups, notes


async def search(
    query: str,
    sources: tuple[str, ...] = DEFAULT_SOURCES,
    limit: int = 5,
    readable_only: bool = False,
    abstract_chars: int = 500,
    max_results: int = 5,
) -> dict:
    """Search `sources`, merge, and return only the `max_results` most relevant records.

    `limit` is how deep each source is searched, which feeds the merge; `max_results` is
    how much of the merged set reaches the caller. They are separate because every record
    returned costs an agent context, and the head of a relevance-ordered list is what a
    user wants. `matched` and `more_available` say what was left out.
    """
    async with client() as c:
        groups, notes = await _gather(c, query, sources, limit)
    records = merge(groups)
    if readable_only:
        records = [r for r in records if r.readable]
    matched = len(records)
    records = records[:max_results]
    mix: dict[str, int] = {}
    for r in records:
        mix[r.access_route.value] = mix.get(r.access_route.value, 0) + 1
    return {
        "query": query,
        "sources": list(sources),
        "count": len(records),
        "matched": matched,
        "more_available": matched > len(records),
        "readable": sum(1 for r in records if r.readable),
        "access_mix": mix,
        "ordering": (
            "Relevance, interleaved across sources. Access route breaks ties only, so a "
            "record you cannot read may well be the best answer — present these together "
            "and let the user choose, rather than leading with whatever happens to be open. "
            "These are the most relevant of `matched`; if more_available, tell the user "
            "how many more there are and offer them instead of fetching them unasked."
        ),
        "records": [r.to_dict(abstract_chars) for r in records],
        "notes": notes,
    }


async def read(record_id: str, question: str = "", max_chars: int = 6000) -> dict:
    """Full text for a record, reduced to the passages that answer `question`."""
    prefix, _, ident = record_id.partition(":")
    async with client() as c:
        if prefix == "vtechworks":
            record, text = await vtechworks.fetch_text(c, ident)
        elif prefix == "figshare":
            record, text = await figshare.fetch_text(c, ident)
        elif prefix in ("openalex", "primo", "primo_catalog"):
            return _metadata_only(record_id)
        else:
            return {"id": record_id, "error": f"unknown record id prefix '{prefix}'"}

    base = {
        "id": record.id,
        "title": record.title,
        "authors": record.authors[:8],
        "year": record.year,
        "doi": record.doi,
        "cite_uri": record.cite_uri,
        "access_route": record.access_route.value,
    }
    extracted_nothing = bool(text) and len(text.strip()) < MIN_USABLE_CHARS
    if extracted_nothing:
        text = None
        base["access_route"] = AccessRoute.ABSTRACT_ONLY.value

    if not text:
        return {
            **base,
            "text_available": False,
            "abstract": clamp(record.abstract, 1200),
            "guidance": EMPTY_EXTRACTION
            if extracted_nothing
            else NOT_READABLE.get(
                record.access_route, NOT_READABLE[AccessRoute.ABSTRACT_ONLY]
            ),
        }

    passages = rank(text, question, max_chars)
    returned = sum(len(p.text) for p in passages)
    return {
        **base,
        "text_available": True,
        "question": question,
        "chars_total": len(text),
        "text_truncated_upstream": len(text) >= 100_000,
        "chars_returned": returned,
        "passages": [p.text for p in passages],
        "coverage": (
            f"{returned} of {len(text)} characters, selected against the question"
            if question
            else f"opening {returned} of {len(text)} characters; no question was given"
        ),
    }


def _metadata_only(record_id: str) -> dict:
    return {
        "id": record_id,
        "text_available": False,
        "guidance": (
            "Records from this source are discovery metadata only. If it has a DOI, call "
            "resolve to check for a legal open copy, and search vtechworks for a VT-"
            "deposited manuscript before handing the user off."
        ),
    }


async def resolve(doi: str) -> dict:
    """DOI to open-access status. One OpenAlex call, ~2 KB, no Unpaywall round trip."""
    from .models import normalize_doi

    bare = normalize_doi(doi)
    if not bare:
        return {"doi": doi, "error": "not a DOI"}
    async with client() as c:
        record = await openalex.by_doi(c, bare)
    if record is None:
        return {"doi": bare, "found": False}
    out = record.to_dict(abstract_chars=800)
    out["found"] = True
    out["vt_dataset"] = bare.startswith(VT_DOI_PREFIX)
    return out
