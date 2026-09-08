"""VTechWorks (DSpace 7.6.1) — VT's own output, and the only source whose full text
this service can actually read.

DSpace pre-extracts plaintext into a `TEXT` bundle beside `ORIGINAL`, so full text
arrives as clean UTF-8 with no PDF parsing anywhere. `embed=bundles/bitstreams` folds
what used to be a three-hop chain into the search call, which is how a record's
`access_route` is known to be real rather than assumed.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import DSPACE, MAX_TEXT_BYTES
from ..models import AccessRoute, Record, normalize_doi, normalize_type


def _meta(obj: dict, key: str) -> list[str]:
    entries = (obj.get("metadata") or {}).get(key) or []
    return [e["value"] for e in entries if isinstance(e, dict) and e.get("value")]


def _one(obj: dict, key: str) -> str | None:
    vals = _meta(obj, key)
    return vals[0] if vals else None


def _unwrap(node: Any, key: str) -> list[dict]:
    """DSpace nests embedded collections as {_embedded: {<key>: [...]}}."""
    if isinstance(node, dict):
        node = node.get("_embedded", {}).get(key, node)
    return node if isinstance(node, list) else []


def text_bitstream(item: dict) -> dict | None:
    """The `TEXT` bundle's first bitstream, from an embedded search result.

    Absent means the item has no extracted text. That item is abstract-only, and saying
    otherwise is the mistake this whole field exists to prevent.
    """
    bundles = _unwrap((item.get("_embedded") or {}).get("bundles"), "bundles")
    for bundle in bundles:
        if bundle.get("name") != "TEXT":
            continue
        streams = _unwrap(
            (bundle.get("_embedded") or {}).get("bitstreams"), "bitstreams"
        )
        if streams:
            return streams[0]
    return None


def _year(raw: str | None) -> int | None:
    if raw and len(raw) >= 4 and raw[:4].isdigit():
        return int(raw[:4])
    return None


def to_record(item: dict, rank: int = 0) -> Record:
    handle = item.get("handle")
    bitstream = text_bitstream(item)
    return Record(
        id=f"vtechworks:{item['uuid']}",
        title=_one(item, "dc.title") or item.get("name") or "(untitled)",
        source="vtechworks",
        access_route=(
            AccessRoute.VTECHWORKS_TEXT if bitstream else AccessRoute.ABSTRACT_ONLY
        ),
        authors=_meta(item, "dc.contributor.author"),
        year=_year(_one(item, "dc.date.issued")),
        type=normalize_type(_one(item, "dc.type")),
        doi=normalize_doi(_one(item, "dc.identifier.doi")),
        abstract=_one(item, "dc.description.abstract"),
        cite_uri=f"https://hdl.handle.net/{handle}" if handle else None,
        rank=rank,
    )


async def search(client: httpx.AsyncClient, query: str, limit: int = 5) -> list[Record]:
    resp = await client.get(
        f"{DSPACE}/discover/search/objects",
        params={
            "query": query,
            "dsoType": "item",
            "size": limit,
            # Costs ~15 KB per item on the wire and nothing in anyone's context. Buys a
            # truthful access_route without a round trip per result.
            "embed": "bundles/bitstreams",
        },
    )
    resp.raise_for_status()
    objects = (
        resp.json().get("_embedded", {}).get("searchResult", {}).get("_embedded", {})
    ).get("objects") or []
    out = []
    for i, wrapper in enumerate(objects):
        item = (wrapper.get("_embedded") or {}).get("indexableObject")
        if item and item.get("uuid"):
            out.append(to_record(item, rank=i))
    return out


async def fetch_item(client: httpx.AsyncClient, uuid: str) -> dict:
    resp = await client.get(
        f"{DSPACE}/core/items/{uuid}", params={"embed": "bundles/bitstreams"}
    )
    resp.raise_for_status()
    return resp.json()


async def fetch_text(client: httpx.AsyncClient, uuid: str) -> tuple[Record, str | None]:
    """Resolve an item to its extracted plain text. Returns (record, text-or-None)."""
    item = await fetch_item(client, uuid)
    record = to_record(item)
    bitstream = text_bitstream(item)
    if not bitstream:
        return record, None
    if (bitstream.get("sizeBytes") or 0) > MAX_TEXT_BYTES:
        return record, None
    href = bitstream["_links"]["content"]["href"]
    resp = await client.get(href, follow_redirects=True)
    resp.raise_for_status()
    return record, resp.text
