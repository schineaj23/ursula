"""VT Data Repository, via global Figshare.

Two things the public API gets wrong for VT, both established by live probing:
`group_id` does not identify VT (records span 23+ groups), and topical search does not
reach VT's corpus at all. The DOI prefix is the only reliable institutional filter, and
an empty result means "not found", never "VT has no such data".

Search results omit description, authors and files, so hits are enriched here — one
detail call per kept record, server-side, where the bytes do not matter.
"""

from __future__ import annotations

import asyncio

import httpx

from ..config import FIGSHARE, VT_DOI_PREFIX
from ..models import AccessRoute, Record, normalize_doi, normalize_type

#: Extensions worth handing to a model as text. Everything else is a download link.
TEXTUAL = (".txt", ".csv", ".tsv", ".md", ".json", ".xml", ".r", ".py", ".yml", ".yaml")

SEARCH_POOL = 100
"""VT is a rounding error inside global Figshare, so cast wide and filter locally."""


def _year(raw: str | None) -> int | None:
    if raw and len(raw) >= 4 and raw[:4].isdigit():
        return int(raw[:4])
    return None


def to_record(article: dict, rank: int = 0) -> Record:
    files = article.get("files") or []
    return Record(
        id=f"figshare:{article['id']}",
        title=article.get("title") or "(untitled)",
        source="vtdr",
        access_route=(
            AccessRoute.FIGSHARE_FILE if files else AccessRoute.ABSTRACT_ONLY
        ),
        authors=[
            a["full_name"] for a in (article.get("authors") or []) if a.get("full_name")
        ],
        year=_year(article.get("published_date")),
        type=normalize_type(article.get("defined_type_name")),
        doi=normalize_doi(article.get("doi")),
        abstract=article.get("description"),
        cite_uri=article.get("url_public_html"),
        rank=rank,
    )


async def detail(client: httpx.AsyncClient, article_id: int | str) -> dict:
    resp = await client.get(f"{FIGSHARE}/articles/{article_id}")
    resp.raise_for_status()
    return resp.json()


async def search(client: httpx.AsyncClient, query: str, limit: int = 5) -> list[Record]:
    resp = await client.post(
        f"{FIGSHARE}/articles/search",
        json={"search_for": query, "limit": SEARCH_POOL},
    )
    resp.raise_for_status()
    hits = [
        a for a in (resp.json() or []) if (a.get("doi") or "").startswith(VT_DOI_PREFIX)
    ][:limit]
    if not hits:
        return []
    full = await asyncio.gather(
        *(detail(client, a["id"]) for a in hits), return_exceptions=True
    )
    out = []
    for i, (stub, rich) in enumerate(zip(hits, full)):
        out.append(to_record(rich if isinstance(rich, dict) else stub, rank=i))
    return out


async def fetch_text(
    client: httpx.AsyncClient, article_id: str
) -> tuple[Record, str | None]:
    """Return the record and, when one of its files is plainly textual, that file."""
    article = await detail(client, article_id)
    record = to_record(article)
    for f in article.get("files") or []:
        name = (f.get("name") or "").lower()
        url = f.get("download_url")
        if url and name.endswith(TEXTUAL):
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            return record, resp.text
    return record, None
