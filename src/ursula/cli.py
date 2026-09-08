"""Command line face — for local testing, and for use from a skill in a host that can
run code. `search` and `read` print the same JSON the HTTP and MCP faces return."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import core


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ursula", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_search = sub.add_parser("search", help="search VT's library sources")
    p_search.add_argument("query")
    p_search.add_argument(
        "--sources",
        default="",
        help=f"comma-separated; any of {', '.join(core.SOURCES)}",
    )
    p_search.add_argument("--limit", type=int, default=5)
    p_search.add_argument("--readable-only", action="store_true")

    p_read = sub.add_parser("read", help="read a record's full text as ranked passages")
    p_read.add_argument("id", help="a record id from search, e.g. vtechworks:<uuid>")
    p_read.add_argument("--question", default="")
    p_read.add_argument("--max-chars", type=int, default=6000)

    p_resolve = sub.add_parser("resolve", help="DOI to open-access status")
    p_resolve.add_argument("doi")

    p_serve = sub.add_parser("serve", help="run the HTTP shim")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("ursula.http_api:app", host=args.host, port=args.port)
        return 0

    if args.cmd == "search":
        chosen = tuple(s.strip() for s in args.sources.split(",") if s.strip())
        result = asyncio.run(
            core.search(
                args.query,
                chosen or core.DEFAULT_SOURCES,
                args.limit,
                args.readable_only,
            )
        )
    elif args.cmd == "read":
        result = asyncio.run(core.read(args.id, args.question, args.max_chars))
    else:
        result = asyncio.run(core.resolve(args.doi))

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
