from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import core

mcp = MCPServer(
    "ursula",
    title="Ursula — VT library research",
    version="0.1.0",
    instructions=(
        "Search Virginia Tech's library sources, then read what is readable and link "
        "what is not. When a request is broad, ask the user to narrow it before "
        "searching, and present the few most relevant results rather than everything "
        "found. Primo tells you what exists; VTechWorks and OpenAlex tell you what "
        "can be read. Rank by relevance rather than by access, since the best answer is "
        "often paywalled, and respect every record's access_route: never state or imply "
        "you have read something you have only found."
    ),
)


@mcp.tool()
async def ursula_search(
    query: str,
    sources: str = "",
    limit: int = 5,
    readable_only: bool = False,
    max_results: int = 5,
) -> dict:
    """Search Virginia Tech's library sources and return the most relevant few records.

    If the request is broad ("papers on climate change"), ask the user to narrow it
    before calling: the angle they care about, what it is for, the kind of material,
    any date or discipline constraints. Skip that when the request is already specific.

    `query` is plain keywords, three to six substantive nouns. Boolean operators and
    question phrasing both hurt recall.

    `max_results` (default 5, up to 20) is how many merged records come back; `limit` is
    only how deep each source is searched. Keep the default. `matched` and
    `more_available` say what was left out: offer it to the user rather than fetching
    it unasked, and if the top results are off-target, refine the query instead.

    `sources` is a comma-separated subset of primo, primo_catalog, vtechworks, openalex,
    vtdr; it defaults to primo, vtechworks and openalex. Primo has the broadest coverage
    and is mostly unreadable. VTechWorks is VT's repository and the only readable full
    text. OpenAlex finds legal open copies. vtdr is datasets. primo_catalog is books and
    physical holdings.

    Results are ordered by relevance, interleaved across sources; access route is a
    tiebreak worth about one position, not a ranking. Do not privilege what you can read.
    A paywalled article the user can reach by signing in is frequently the best answer,
    and `access_mix` shows the spread you have. `readable_only` discards everything else
    and is rarely what you want.

    Every record carries `access_route` and `readable`. Never state or imply you have
    read something whose route is `abstract_only`, `oa_pdf` or `licensed_handoff`.
    An `also_in` list means the same work was found in more than one source, which is
    usually a paywalled article whose accepted manuscript VT deposited: cite the
    published version, read the VT copy, and say that is what you did.
    """
    chosen = tuple(s.strip() for s in sources.split(",") if s.strip())
    return await core.search(
        query,
        chosen or core.DEFAULT_SOURCES,
        limit,
        readable_only,
        max_results=max_results,
    )


@mcp.tool()
async def ursula_read(id: str, question: str = "", max_chars: int = 6000) -> dict:
    """Read a record's full text, reduced to the passages answering `question`.

    `id` is a record id from ursula_search, such as `vtechworks:2f0e…`. Only records
    marked `readable` have text; the rest come back with guidance on what to do instead.
    Pass the user's actual question, since passages are ranked against it.
    """
    return await core.read(id, question, max_chars)


@mcp.tool()
async def ursula_resolve(doi: str) -> dict:
    """Check whether a DOI has a legal open-access copy, and where.

    Accepts a bare DOI or a doi.org URL. Use it on anything Primo surfaced behind a
    subscription before handing the user off to the library.
    """
    return await core.resolve(doi)


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="ursula-mcp", description="Ursula as an MCP server."
    )
    parser.add_argument(
        "--http", action="store_true", help="serve streamable HTTP instead of stdio"
    )
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args(argv)
    if args.http:
        mcp.run("streamable-http", port=args.port)
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()
