"""OpenAlex — global scholarly metadata with trustworthy open-access status.

It complements Primo rather than duplicating it: Primo knows what VT licenses, OpenAlex
knows what is freely readable. `select=` is a 4x payload reduction and is never omitted.
"""

from __future__ import annotations

import httpx

from ..config import MAILTO, OPENALEX
from ..models import AccessRoute, Record, normalize_doi, normalize_type

SELECT = (
    "id,doi,title,publication_year,type,open_access,"
    "primary_location,authorships,abstract_inverted_index"
)


def _abstract(inverted: dict | None) -> str | None:
    """OpenAlex ships abstracts as a word -> positions index. Rebuild it here, once,
    where it costs nothing, instead of pushing the index at a model."""
    if not inverted:
        return None
    slots: list[tuple[int, str]] = []
    for word, positions in inverted.items():
        for pos in positions:
            slots.append((pos, word))
    if not slots:
        return None
    slots.sort()
    return " ".join(word for _, word in slots)


def to_record(work: dict, rank: int = 0) -> Record:
    oa = work.get("open_access") or {}
    location = work.get("primary_location") or {}
    is_oa = bool(oa.get("is_oa"))
    return Record(
        id=f"openalex:{(work.get('id') or '').rsplit('/', 1)[-1]}",
        title=work.get("title") or "(untitled)",
        source="openalex",
        # Not open does not mean VT licenses it. Primo is what knows that, so the
        # honest floor here is abstract_only and a merge can only raise it.
        access_route=AccessRoute.OA_PDF if is_oa else AccessRoute.ABSTRACT_ONLY,
        authors=[
            a["author"]["display_name"]
            for a in (work.get("authorships") or [])
            if a.get("author", {}).get("display_name")
        ],
        year=work.get("publication_year"),
        type=normalize_type(work.get("type")),
        doi=normalize_doi(work.get("doi")),
        abstract=_abstract(work.get("abstract_inverted_index")),
        cite_uri=location.get("landing_page_url")
        or (
            f"https://doi.org/{normalize_doi(work.get('doi'))}"
            if work.get("doi")
            else None
        ),
        oa_url=oa.get("oa_url"),
        rank=rank,
    )


def _params(**extra) -> dict:
    params = {"select": SELECT, **extra}
    if MAILTO:
        params["mailto"] = MAILTO
    return params


async def search(client: httpx.AsyncClient, query: str, limit: int = 5) -> list[Record]:
    resp = await client.get(
        f"{OPENALEX}/works", params=_params(search=query, **{"per-page": limit})
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    return [to_record(w, rank=i) for i, w in enumerate(results)]


async def by_doi(client: httpx.AsyncClient, doi: str) -> Record | None:
    """DOI lookup as a query parameter, which is also why Unpaywall is not needed —
    `open_access.oa_url` is the same fact in one fewer round trip."""
    resp = await client.get(
        f"{OPENALEX}/works", params=_params(filter=f"doi:{doi}", **{"per-page": 1})
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    return to_record(results[0]) if results else None
