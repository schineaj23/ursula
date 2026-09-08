"""The normalized record. See reference/record-shape.md — this is that contract, in code."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class AccessRoute(str, Enum):
    """How — and whether — the text behind a record can actually be read.

    An enum rather than a boolean, because "can I read this" has five different
    answers with five different follow-up actions.
    """

    VTECHWORKS_TEXT = "vtechworks_text"
    FIGSHARE_FILE = "figshare_file"
    OA_PDF = "oa_pdf"
    ABSTRACT_ONLY = "abstract_only"
    LICENSED_HANDOFF = "licensed_handoff"


#: Higher wins a merge, and sorts higher in a result set. Text beats a link to text.
READABILITY = {
    AccessRoute.VTECHWORKS_TEXT: 4,
    AccessRoute.FIGSHARE_FILE: 3,
    AccessRoute.OA_PDF: 2,
    AccessRoute.ABSTRACT_ONLY: 1,
    AccessRoute.LICENSED_HANDOFF: 0,
}

#: Routes whose text `read()` can genuinely return.
FETCHABLE = {AccessRoute.VTECHWORKS_TEXT, AccessRoute.FIGSHARE_FILE}

TYPES = ("article", "thesis", "dataset", "report", "book", "other")

_TYPE_HINTS = (
    ("dissertation", "thesis"),
    ("thesis", "thesis"),
    ("etd", "thesis"),
    ("dataset", "dataset"),
    ("data", "dataset"),
    ("software", "dataset"),
    ("book", "book"),
    ("report", "report"),
    ("technical", "report"),
    ("article", "article"),
    ("journal", "article"),
    ("paper", "article"),
    ("conference", "article"),
    ("preprint", "article"),
)


def normalize_type(raw: str | None) -> str:
    if not raw:
        return "other"
    low = raw.lower()
    for needle, out in _TYPE_HINTS:
        if needle in low:
            return out
    return "other"


def normalize_doi(raw: str | None) -> str | None:
    """Bare lowercase DOI. OpenAlex hands them back as full URLs; Primo does not."""
    if not raw:
        return None
    doi = raw.strip().lower()
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi)
    doi = doi.removeprefix("doi:").strip()
    return doi or None


_ARTICLES = {"a", "an", "the"}


def title_key(title: str) -> str:
    """Loose title key for merging when no DOI is available on both sides."""
    words = re.findall(r"[a-z0-9]+", title.lower())
    return " ".join(w for w in words if w not in _ARTICLES)


def dedupe_title(title: str) -> str:
    """Primo repeats titles in-field as "Title: Title". Collapse that."""
    t = " ".join(title.split())
    for sep in (": ", " - ", " | "):
        if sep in t:
            head, _, tail = t.partition(sep)
            if head and title_key(head) == title_key(tail):
                return head
    half = len(t) // 2
    if len(t) % 2 == 0 and t[:half].strip() == t[half:].strip():
        return t[:half].strip()
    return t


def clamp(text: str | None, limit: int) -> str | None:
    """Abstracts are the fattest field worth keeping. Keep them, but bounded."""
    if not text:
        return None
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


@dataclass
class Record:
    id: str
    """Namespaced and round-trippable: `vtechworks:<uuid>`, `primo:<recordid>`,
    `openalex:<W…>`, `figshare:<id>`. Whatever `search` returns here, `read` accepts."""

    title: str
    source: str
    access_route: AccessRoute
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    type: str = "other"
    doi: str | None = None
    abstract: str | None = None
    cite_uri: str | None = None
    oa_url: str | None = None
    rank: int = 0
    """Position in its source's own result list. Preserved so merged sets stay sensible."""

    also_in: list[str] = field(default_factory=list)
    """Other sources holding the same work. The published-vs-deposited pattern lives here."""

    def merge_key(self) -> str:
        if self.doi:
            return f"doi:{self.doi}"
        return f"title:{title_key(self.title)}|{self.year or ''}"

    @property
    def readable(self) -> bool:
        return self.access_route in FETCHABLE

    def to_dict(self, abstract_chars: int = 500) -> dict:
        out = {
            "id": self.id,
            "title": self.title,
            "authors": self.authors[:8],
            "year": self.year,
            "type": self.type,
            "doi": self.doi,
            "source": self.source,
            "access_route": self.access_route.value,
            "readable": self.readable,
        }
        if len(self.authors) > 8:
            out["authors_truncated"] = len(self.authors)
        if self.abstract:
            out["abstract"] = clamp(self.abstract, abstract_chars)
        if self.cite_uri:
            out["cite_uri"] = self.cite_uri
        if self.oa_url:
            out["oa_url"] = self.oa_url
        if self.also_in:
            out["also_in"] = self.also_in
        return out
