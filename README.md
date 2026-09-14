# Ursula

**Use this agent in HokieAI [here](https://hokie.ai.vt.edu/chat/642acc22-7caf-432f-ae10-e886e05a564a)!**

Library research for Virginia Tech University Libraries. Ursula searches VT's discovery
layer, institutional repository, data repository and the open-access literature, and returns
compact, normalized results an AI agent can use without blowing its context window.

It does three things:

| Function | What it does |
|---|---|
| `search` | Search all sources at once; returns the five most relevant merged, deduplicated results |
| `read` | Fetch a document's full text, reduced to the passages that answer a question |
| `resolve` | Check whether a DOI has a legal open-access copy, and where |

The same three functions are available as an **HTTP API** (NebulaONE, Open WebUI), an
**MCP server** (Claude Code, Claude Desktop, Cursor, prime-agent) and a **CLI**.

## Sources

| Source | What it gives |
|---|---|
| Primo VE | The library's discovery layer: licensed articles, ebooks, catalog |
| VTechWorks | VT theses, dissertations, preprints, accepted manuscripts, with full text |
| OpenAlex | Scholarly metadata and open-access status worldwide |
| VT Data Repository (Figshare) | VT datasets |

No API keys are required.

## Install

```sh
uv venv && uv pip install -e ".[all,dev]"
export URSULA_MAILTO=you@vt.edu   # recommended: puts OpenAlex calls in the polite pool
```

Install only what you need with `.[http]` or `.[mcp]` instead of `.[all]`.

## Usage

### CLI

```sh
ursula search "machine learning soil moisture"
ursula search "soil moisture" --sources vtechworks,openalex --max-results 10
ursula read vtechworks:<uuid> --question "what accuracy was reported"
ursula resolve <doi>                # bare DOI or doi.org URL
```

Output is JSON on stdout. Run `ursula <command> --help` for all options.

### HTTP API

```sh
ursula serve                       # http://127.0.0.1:8000
ursula serve --host 0.0.0.0 --port 8080
```

| Endpoint | Parameters |
|---|---|
| `GET /search` | `query`, `sources`, `max_results` (1–20, default 5), `limit` (per-source depth, 1–20), `readable_only` |
| `GET /read` | `id`, `question`, `max_chars` (200–40000) |
| `GET /resolve` | `doi` |
| `GET /health` | — |

Or in Docker, which serves on port 8000:

```sh
docker build -t ursula .
docker run --rm -p 8000:8000 -e URSULA_MAILTO=you@vt.edu ursula
```

The OpenAPI schema is at `/openapi.json`. To set Ursula up as a NebulaONE agent, register
the endpoints as described in [`agent/endpoints.md`](agent/endpoints.md) and use
[`agent/system-prompt.md`](agent/system-prompt.md) as the agent's prompt.

### MCP server

```sh
ursula-mcp                         # stdio
ursula-mcp --http --port 8001      # streamable HTTP
```

For example, in Claude Code:

```sh
claude mcp add ursula -- ursula-mcp
```

This exposes the tools `ursula_search`, `ursula_read` and `ursula_resolve`.

## Search sources

`sources` takes a comma-separated subset of these. The default is `primo,vtechworks,openalex`.

| Name | Use it for |
|---|---|
| `primo` | Broadest coverage; mostly not readable |
| `primo_catalog` | Books and physical holdings |
| `vtechworks` | VT's repository; the readable full text |
| `openalex` | Finding legal open copies |
| `vtdr` | Datasets |

## Results

Every record uses the same shape, documented in
[`reference/record-shape.md`](reference/record-shape.md). The key fields:

- **`access_route`**: how the content can be reached. One of `vtechworks_text`,
  `figshare_file`, `oa_pdf`, `abstract_only` or `licensed_handoff`.
- **`readable`**: whether `read` can return full text for this record.
- **`cite_uri`**: a link to send a person to, including for paywalled items a VT user can
  reach by signing in.
- **`oa_url`**: a legal open-access copy, where one exists.
- **`also_in`**: other sources where the same work turned up, often a VT-deposited copy
  of a paywalled article.

Search responses also include `matched` and `more_available` (how many relevant results
were left out), `access_mix` (how many returned results fall under each route) and `notes`
(for example, a source that failed).

## Known limitations

- **Dataset search has low recall.** Figshare's public search rarely surfaces VT datasets.
- **VTechWorks full text stops at 100,000 characters.** Longer documents are cut off by
  the repository; `read` reports this as `text_truncated_upstream`.
- **Scans without OCR have no text.** `read` reports these as abstract-only.
- **Primo is queried through an undocumented endpoint.** It works today but may change
  without notice.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `URSULA_MAILTO` | — | Contact email sent to OpenAlex |
| `URSULA_TIMEOUT` | `45` | Upstream request timeout, in seconds |
| `URSULA_MAX_TEXT_BYTES` | 8 MiB | Largest full text the service will fetch |

## Development

```sh
pytest           # offline: parsers, merging, ranking, HTTP contract
pytest --live    # also calls the real upstream APIs
```

Code layout:

- `src/ursula/sources/`: one module per upstream API
- `src/ursula/core.py`: merging and dispatch
- `src/ursula/rank.py`: passage selection for `read`
- `src/ursula/cli.py`, `http_api.py`, `mcp_server.py`: thin wrappers over `core`

For more on the upstream APIs, see [`reference/upstream-apis.md`](reference/upstream-apis.md).
