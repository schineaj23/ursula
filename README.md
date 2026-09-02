# Ursula

A library research agent for Virginia Tech, built for the **NebulaONE** platform.

NebulaONE agents are a system prompt plus a set of registered HTTP endpoints. There is no
filesystem and no code between the model and the API, so every design decision here is
shaped by one constraint: **whatever an endpoint returns lands directly in the context
window.**

## Status: v0 — no infrastructure required

v0 uses only sources that are keyless and directly registrable — no infrastructure, no keys,
no approvals. It covers VT's licensed holdings, VT's own research output, and the
open-access literature.

| Source | What it gives | Auth | Verified |
|---|---|---|---|
| Primo VE (`/pnxs`) | The library's discovery layer — licensed articles, ebooks, catalog | none | ✅ live ⚠️ undocumented |
| VTechWorks (DSpace 7.6.1) | VT theses, dissertations, preprints, accepted manuscripts — **with extracted full text** | none | ✅ live |
| OpenAlex | Scholarly metadata + OA location, for anything not VT-authored | none | ✅ live |
| VT Data Repository (Figshare) | VT datasets | none | ⚠️ low recall — see below |
| Unpaywall | DOI → legal OA copy | email param | ⚠️ untested |

The division that shapes the whole agent: **Primo tells you what exists, VTechWorks and
OpenAlex tell you what can actually be read.** Neither alone is the answer.

## Getting started

```sh
./probes/probe.sh              # smoke-test every v0 endpoint
./probes/probe.sh --email you@vt.edu   # also exercises Unpaywall
```

Then register the endpoints in NebulaONE per [`agent/endpoints.md`](agent/endpoints.md) and
paste [`agent/system-prompt.md`](agent/system-prompt.md) as the agent's prompt.

## What the live probes established

Endpoint behaviour was measured, not assumed. Full detail in
[`reference/survey-corrections.md`](reference/survey-corrections.md); the two that change
the design:

**VT's Figshare records are not identified by `group_id`.** A prior survey recommended
filtering on `group_id == 32433`. In a 100-record sample, VT DOIs spanned **23 distinct
group_ids**, and 32433 accounted for exactly one of them. The `group` and `institution`
filters on the search endpoint both return empty. The reliable VT filter is the **DOI
prefix `10.7294`**, applied client-side.

**Payload size is the binding constraint, not rate limits or auth.** Measured:

| Call | Size | Per unit |
|---|---|---|
| Primo `/pnxs`, `limit=1` / `5` / `10` | 21 / **91** / 172 KB | ~17.5 KB/record |
| DSpace search, `size=2` | 44.0 KB | ~14 KB/item over ~16 KB fixed overhead |
| DSpace search, `size=5` | 86.3 KB | (`size=10` extrapolates to ~157 KB — don't) |
| OpenAlex works, raw | 41.5 KB / 2 works | ~20 KB/work |
| OpenAlex works, with `select=` | 28.3 KB / 5 works | ~5.6 KB/work |
| Figshare search | 25.5 KB / 25 items | ~1.0 KB/item |
| DSpace `TEXT` bitstream (one article) | 100.4 KB | 15,191 words |

The `select=` parameter on OpenAlex is not optional — it is a 4× reduction. Use it always.

**Figshare topical search does not reach VT.** VT's corpus is a rounding error inside global
Figshare, and the public search index does not surface it: `"soil moisture"` at `limit=25`
returned 25 records and **zero** with VT's `10.7294` prefix. Adding `"Virginia Tech"` to the
query returns nothing at all (the terms AND together). The `group` and `institution` body
filters return empty, and `:group:` search syntax is ignored. Only `GET /v2/articles?group=`
works — 13 records for group 32433, all genuinely VT — but that lists, it cannot search, and
VT spans 23+ groups with no public endpoint to enumerate them.

So Figshare stays in v0 for known-item and browse use, and the agent is told not to promise
dataset coverage. Fixing this properly needs VT's Figshare **institution ID**, which turns
the open question below into the blocker for dataset discovery.

**The full-text path works exactly as hoped.** A DSpace item carries a `TEXT` bundle beside
`ORIGINAL`, holding the plain text DSpace extracted for its own indexing. It returns as
`text/plain; charset=UTF-8`, clean, no PDF parsing anywhere. This is the single best thing
about the whole integration.

It is also the main cost centre. That 100 KB was a journal article. ETDs — VTechWorks' bulk
and its most distinctive holding — are dissertations, and run several times larger. **Budget
roughly one full-text read per conversation** and work from abstracts otherwise. This is the
limitation v1 is designed to remove.

## Architecture

```
        ┌─ VTechWorks ───┐
prompt ─┼─ Figshare ─────┼─→ normalize ─→ merge ─→ resolve ─→ read
        └─ OpenAlex ─────┘   (in prompt)   on DOI   Unpaywall   TEXT bundle
```

In v0 every box after the sources lives in the system prompt — the model does the
normalizing and merging itself, which works because NebulaONE runs a real multi-step tool
loop. The [normalized record contract](reference/record-shape.md) is what makes that
tractable: three sources describe the same object in three vocabularies, and the agent
converts to one shape before reasoning.

`access_route` is the load-bearing field. It is an enum, never a boolean:

```
vtechworks_text | figshare_file | oa_pdf | abstract_only | licensed_handoff
```

Every honesty guarantee the agent makes derives from that field existing — it is how the
agent says "full text from VTechWorks" versus "abstract only, sign in to read" instead of
silently returning less than the user assumes.

## Roadmap

**v0 — now.** The four sources above. No infrastructure, no keys, no approvals.

**v0.1 — swap Primo's transport.** Get an Ex Libris Developer Network API key and move to
the supported `/primo/v1/search`. Since NebulaONE injects API keys, this is a re-registration
rather than a rewrite — which is precisely why Primo is two named endpoints and not
hand-built query strings scattered through the prompt. Keys are administered by library
systems staff; `discovery-g@vt.edu` is the published contact. This retires the
undocumented-endpoint risk and the acceptable-use question in one move, so it is worth
starting the request now even though v0 works without it.

**v1 — a small hosted service**, two endpoints (`/search`, `/read`), doing two jobs:
normalize the four vocabularies server-side, and return **ranked passages rather than whole
documents**. The second is the point. The first is a nicety.

The number that justifies building it is 100 KB — one journal article's full text — not
anything about Primo. Until passages are ranked server-side, the agent reads one document
per conversation, and that is the ceiling on how good it can be.

**v2 — keyed sources.** Alma availability, LibAnswers as a knowledge source, ILLiad as the
concrete next action whenever `access_route == licensed_handoff`.

## Open questions

- Does VT Libraries have an active Ex Libris Developer Network account, and who administers
  the keys?
- Which publisher agreements carry text-and-data-mining clauses? This sets the real ceiling
  on full-text depth for licensed content.
- **What is VT's Figshare institution ID?** Now blocking, not cosmetic — without it there is
  no working topical search over VT's datasets at all. Data Services should know it. Ask at
  the same time whether they can enumerate VT's Figshare group ids.
- What is NebulaONE's response size cap? See [`probes/README.md`](probes/README.md) for the
  test — it decides whether Primo needs a proxy or merely wastes tokens.
