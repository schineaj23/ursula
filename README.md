# Ursula

A library research capability for Virginia Tech University Libraries: three functions over
VT's discovery layer, institutional repository, data repository and the open-access
literature, normalized to one record shape.

```
search  →  find across four sources, merged and deduplicated
read    →  a document's full text, reduced to the passages that answer a question
resolve →  a DOI's open-access status
```

It runs three ways from one core. An **HTTP service** for NebulaONE and VT's Open WebUI, an
**MCP server** for agents run locally in Claude Code, prime-agent, Claude Desktop or Cursor,
and a **CLI** for a skill in any host that can run a shell.

## Why a service and not a set of registered endpoints

The first version of this registered the ten upstream APIs directly with NebulaONE. Two
things killed that, and both were worth learning.

**Payload size.** NebulaONE agents are a prompt plus registered endpoints, with no
filesystem and no code between the model and the API, so whatever an endpoint returns lands
directly in the context window. One Primo search is 91 KB. One VTechWorks search is 86 KB.
One article's extracted full text is 100 KB, which an agent can afford roughly once.

**NebulaONE registers only `?param=value` URLs.** Five of the ten endpoints took a path
segment, including the entire VTechWorks full-text chain.

Both point the same way. A small service in front of the sources satisfies the second
constraint and dissolves the first:

| | Raw endpoints | Through Ursula |
|---|---|---|
| Four-source search | ~205 KB | **17 KB** |
| One document read | 100 KB | **4 KB** |
| Full-text reads per conversation | 1 | many |

The second row is the point. Until passages are ranked server-side, an agent reads one
document per conversation, and that is the ceiling on how good it can be.

The lowest common denominator NebulaONE forces — flat query parameters, JSON out — turns
out to be exactly what every other host can call too. The constraint produced the portable
API rather than taxing it.

## Sources

| Source | What it gives | Auth |
|---|---|---|
| Primo VE (`/pnxs`) | The library's discovery layer — licensed articles, ebooks, catalog | none ⚠️ undocumented |
| VTechWorks (DSpace 7.6.1) | VT theses, dissertations, preprints, accepted manuscripts — **with extracted full text** | none |
| OpenAlex | Scholarly metadata and open-access status worldwide | none |
| VT Data Repository (Figshare) | VT datasets | none ⚠️ low recall |

The division that shapes everything: **Primo tells you what exists, VTechWorks and OpenAlex
tell you what can actually be read.** Neither alone is the answer.

Unpaywall is gone. OpenAlex answers the same question in one call, and its `filter=doi:`
form is a query parameter rather than a path segment.

## Getting started

```sh
uv venv && uv pip install -e ".[all,dev]"
export URSULA_MAILTO=you@vt.edu     # puts OpenAlex calls in the polite pool

ursula search "machine learning soil moisture"
ursula read vtechworks:<uuid> --question "what accuracy was reported"
ursula serve                        # http://127.0.0.1:8000, OpenAPI at /openapi.json

pytest                              # offline: parsers, merging, ranking, HTTP contract
pytest --live                       # also calls the real upstream APIs
```

Then register it per [`agent/endpoints.md`](agent/endpoints.md) and paste
[`agent/system-prompt.md`](agent/system-prompt.md) as the agent's prompt.

## How it fits together

```
      ┌─ Primo VE ─────┐
      ├─ VTechWorks ───┤                                    ┌─ HTTP  → NebulaONE, Open WebUI
      ├─ OpenAlex ─────┼─→ normalize → merge → rank passages ┼─ MCP   → Claude Code, prime-agent
      └─ Figshare ─────┘   sources/    core.py    rank.py    └─ CLI   → skills, shells
```

`src/ursula/sources/` holds one module per upstream API, each mapping its own vocabulary
into the [normalized record](reference/record-shape.md). `core.py` merges and dispatches.
`rank.py` selects passages. The three faces in `http_api.py`, `mcp_server.py` and `cli.py`
add no behaviour of their own, which is the arrangement worth preserving: VT's routing
rules and honesty guarantees live in one place, not in each host's configuration screen.

`access_route` is the load-bearing field. An enum, never a boolean:

```
vtechworks_text | figshare_file | oa_pdf | abstract_only | licensed_handoff
```

Every honesty guarantee derives from it existing. It is how the agent says "full text from
VTechWorks" rather than silently returning less than the user assumes.

**It is not a quality signal, and results are not sorted by it.** Ranking a result set by
what the service can read buries the most relevant article in the library behind a
marginally relevant one that happens to be open, which quietly narrows a research library
to its free corner. Results come back ordered by relevance and interleaved across sources;
the route is a tiebreak worth about one position. A paywalled article a VT user reaches by
signing in is a good answer, and the response carries a `cite_uri` that gets them there.

The route does decide one thing outright: when the same work turns up twice, the merge
keeps the copy that yields text. The paywalled article whose accepted manuscript VT
deposited is the most valuable pattern in the system, and that is about which copy to
read, not about where the record ranks.

## What live probing established

Behaviour was measured, not assumed. Full detail in
[`reference/survey-corrections.md`](reference/survey-corrections.md) and
[`reference/upstream-apis.md`](reference/upstream-apis.md). Four findings changed the design:

**VT's Figshare records are not identified by `group_id`.** A prior survey recommended
filtering on `group_id == 32433`. In a 100-record sample, VT DOIs spanned 23 distinct
group ids and 32433 accounted for one. The reliable filter is the **DOI prefix `10.7294`**.

**Figshare topical search does not reach VT at all.** VT's corpus is a rounding error inside
global Figshare and the public index does not surface it. Dataset discovery stays degraded
until VT's Figshare institution ID is known, and the agent is told to say "I could not find
it" rather than "VT has no such data."

**DSpace truncates extracted text at 100,000 characters.** Two unrelated documents returned
exactly that; shorter ones return their real length. So a dissertation is readable only down
to its first ~100 KB, whatever its true size. `read` reports `text_truncated_upstream`.

**Some items carry a `TEXT` bundle that extracted to nothing** — a scan with no OCR layer.
One returned a single character. `read` detects this and reports the record as
abstract-only rather than handing back an empty document.

## Roadmap

**Now.** The four sources, three endpoints, no keys and no approvals.

**Hosting and ownership.** The open question, and a bigger risk than any of the code. A
prototype on a personal account is fine until a librarian depends on it; decide who owns it
in production before anyone builds on it.

**Swap Primo's transport.** Get an Ex Libris Developer Network key and move to the
supported `/primo/v1/search`. Only `sources/primo.py` changes. Keys are administered by
library systems staff; `discovery-g@vt.edu` is the published contact. This retires the
undocumented-endpoint risk, and is worth starting now even though the current transport
works.

**Caching.** Extracted text and search results are both highly repeatable and cost a round
trip every time. Cheap to add now, awkward to retrofit.

**Keyed sources.** Alma availability, LibAnswers as a knowledge source, ILLiad as the
concrete next action whenever `access_route` is `licensed_handoff`. This is also when the
hosted service stops being optional: API keys cannot live in a skill on someone's laptop.

## Open questions

- Who owns and hosts the deployed service?
- Does VT Libraries have an active Ex Libris Developer Network account, and who
  administers the keys?
- **What is VT's Figshare institution ID?** Blocking for dataset discovery. Data Services
  should know it. Ask at the same time whether they can enumerate VT's Figshare group ids.
- Which publisher agreements carry text-and-data-mining clauses? This sets the real ceiling
  on full-text depth for licensed content.
- What is NebulaONE's response size cap? See [`probes/README.md`](probes/README.md). Much
  less urgent now that responses are small, but it bounds how large a `limit` or
  `max_chars` is useful.
