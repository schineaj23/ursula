"""Primo VE discovery, via the Discovery UI's own /pnxs endpoint."""

from __future__ import annotations

from typing import Any

import httpx

from ..config import PRIMO_INST, PRIMO_PNXS, PRIMO_VID
from ..models import AccessRoute, Record, dedupe_title, normalize_doi, normalize_type

PRIMO_FULLDISPLAY = "https://virginiatech.primo.exlibrisgroup.com/discovery/fulldisplay"


def _first(node: Any, *path: str) -> str | None:
    cur = node
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    if isinstance(cur, list):
        cur = cur[0] if cur else None
    if isinstance(cur, str):
        return cur.strip() or None
    return None


def _year(raw: str | None) -> int | None:
    if not raw:
        return None
    digits = "".join(c for c in raw if c.isdigit())
    for i in range(len(digits) - 3):
        chunk = digits[i : i + 4]
        if chunk.startswith(("19", "20")):
            return int(chunk)
    return None


def _permalink(record_id: str) -> str:
    """A record's page in Discovery, for when Alma gives us no resolver link.

    Alma-E and catalog records frequently come back with `almaOpenurl: null`, which used
    to leave them with no link at all. Central-index ids carry a `cdi_` prefix; anything
    else is local.
    """
    context = "PC" if record_id.startswith("cdi_") else "L"
    return f"{PRIMO_FULLDISPLAY}?docid={record_id}&vid={PRIMO_VID}&context={context}"


def _route(doc: dict, rec_type: str) -> AccessRoute:
    """Primo states no access route. Two fields imply one.

    `delivery.availability` containing `fulltext` means a signed-in VT user can read it.
    It does not mean this service can. Reading it the other way is the single worst
    mistake available in the whole system.
    """
    display = doc.get("pnx", {}).get("display", {})
    availability = doc.get("delivery", {}).get("availability") or []
    if display.get("oa"):
        return AccessRoute.OA_PDF
    if any("fulltext" in str(a) for a in availability):
        return AccessRoute.LICENSED_HANDOFF
    if rec_type == "book":
        return AccessRoute.LICENSED_HANDOFF
    return AccessRoute.ABSTRACT_ONLY


def parse(payload: dict, limit: int) -> list[Record]:
    records: list[Record] = []
    for i, doc in enumerate(payload.get("docs") or []):
        pnx = doc.get("pnx") or {}
        display = pnx.get("display") or {}
        addata = pnx.get("addata") or {}
        title = _first(display, "title")
        if not title:
            continue
        rec_type = normalize_type(_first(display, "type"))
        rec_id = _first(pnx, "control", "recordid") or doc.get("@id") or f"idx{i}"
        # The resolver link is the better handoff, since it lands on VT's actual access.
        openurl = (doc.get("delivery") or {}).get("almaOpenurl")
        records.append(
            Record(
                id=f"primo:{rec_id}",
                title=dedupe_title(title),
                source="primo",
                access_route=_route(doc, rec_type),
                authors=[
                    a for a in (display.get("creator") or []) if isinstance(a, str)
                ],
                year=_year(_first(display, "creationdate")),
                type=rec_type,
                doi=normalize_doi(_first(addata, "doi")),
                abstract=_first(addata, "abstract"),
                cite_uri=openurl or _permalink(rec_id),
                rank=i,
            )
        )
        if len(records) >= limit:
            break
    return records


async def search(
    client: httpx.AsyncClient, query: str, limit: int = 5, catalog: bool = False
) -> list[Record]:
    params = {
        "vid": PRIMO_VID,
        "inst": PRIMO_INST,
        "lang": "en",
        "q": f"any,contains,{query}",
        "scope": "MyInstitution" if catalog else "MyInst_and_CI",
        "tab": "LibraryCatalog" if catalog else "Everything",
        "offset": 0,
        "limit": max(limit, 10),
        "sort": "rank",
        "pcAvailability": "true",
    }
    resp = await client.get(PRIMO_PNXS, params=params)
    resp.raise_for_status()
    records = parse(resp.json(), limit)
    if catalog:
        for r in records:
            r.source = "primo_catalog"
    return records
