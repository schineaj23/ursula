"""Passage selection.

The number that justifies this whole service is 100 KB — one journal article's extracted
text, and more than an agent can spend more than once. Ranking windows against the actual
question turns that into a few thousand characters, which is what lifts the ceiling of one
document per conversation.

Deliberately dependency-free and lexical. An embedding model would rank better and would
also turn a service anyone can run into one somebody has to operate.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "can",
    "do",
    "does",
    "for",
    "from",
    "has",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "which",
    "who",
    "why",
    "will",
    "with",
    "you",
    "your",
}

WINDOW_CHARS = 1100
MIN_PARAGRAPH = 40


@dataclass
class Passage:
    text: str
    score: float
    position: int
    """Index of the window in the document, so a caller can say where it came from."""


def terms(text: str) -> list[str]:
    return [
        w
        for w in re.findall(r"[a-z0-9][a-z0-9\-']*", text.lower())
        if len(w) > 1 and w not in STOPWORDS
    ]


def _paragraphs(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Extracted PDF text wraps hard at the column width; rejoin lines that plainly
    # continue a sentence, so a window is not half a paragraph.
    text = re.sub(r"(?<![.!?:;])\n(?![\n\s])", " ", text)
    chunks = [" ".join(p.split()) for p in re.split(r"\n\s*\n+", text)]
    return [c for c in chunks if c]


def windows(text: str, size: int = WINDOW_CHARS) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    length = 0
    for para in _paragraphs(text):
        while len(para) > size * 2:
            head, para = para[:size], para[size:]
            out.append(head)
        if length + len(para) > size and buf:
            out.append("\n\n".join(buf))
            buf, length = [], 0
        buf.append(para)
        length += len(para)
    if buf:
        out.append("\n\n".join(buf))
    return [w for w in out if len(w) >= MIN_PARAGRAPH] or out


def rank(text: str, question: str, max_chars: int = 6000) -> list[Passage]:
    """Highest-scoring windows, returned in document order."""
    chunks = windows(text)
    query = list(dict.fromkeys(terms(question)))
    if not chunks:
        return []
    if not query:
        return _head(chunks, max_chars)

    tokenized = [terms(c) for c in chunks]
    n = len(chunks)
    idf = {}
    for term in query:
        df = sum(1 for toks in tokenized if term in toks)
        idf[term] = math.log(1 + n / (1 + df))

    scored: list[Passage] = []
    for i, toks in enumerate(tokenized):
        counts: dict[str, int] = {}
        for t in toks:
            if t in idf:
                counts[t] = counts.get(t, 0) + 1
        if not counts:
            continue
        base = sum((1 + math.log(c)) * idf[t] for t, c in counts.items())
        # A window touching four query terms once beats one repeating a single term.
        coverage = len(counts) / len(query)
        scored.append(Passage(chunks[i], base * (0.4 + coverage), i))

    if not scored:
        return _head(chunks, max_chars)

    scored.sort(key=lambda p: p.score, reverse=True)
    kept: list[Passage] = []
    budget = max_chars
    for p in scored:
        if len(p.text) > budget:
            continue
        kept.append(p)
        budget -= len(p.text)
        if budget < MIN_PARAGRAPH:
            break
    if not kept:
        # Every window is wider than the budget. Return the best one, trimmed, rather
        # than nothing — a caller asking for 400 characters still wants the 400 that
        # answer the question.
        best = scored[0]
        kept = [
            Passage(best.text[:max_chars].rsplit(" ", 1)[0], best.score, best.position)
        ]
    kept.sort(key=lambda p: p.position)
    return kept


def _head(chunks: list[str], max_chars: int) -> list[Passage]:
    """No usable question: the opening of a document is the best default summary."""
    out, budget = [], max_chars
    for i, c in enumerate(chunks):
        if len(c) > budget:
            break
        out.append(Passage(c, 0.0, i))
        budget -= len(c)
    return out
