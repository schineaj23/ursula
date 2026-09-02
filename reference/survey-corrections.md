# Survey corrections

A prior desk survey of VT library APIs informed this design. Before building, every v0
endpoint was called live. Most of the survey held up; three things did not. This file
records the deltas so nobody re-derives them.

Probes run 2 Sep 2026. Re-run with `./probes/probe.sh`.

---

## 1. Figshare: `group_id == 32433` is the wrong VT filter

**Survey said:** search Figshare, then filter results on `group_id == 32433` to get VT
records.

**What actually happens:**

```
POST /v2/articles/search  {"search_for":"soil moisture","group":32433}      → []
POST /v2/articles/search  {"search_for":"soil","institution":32433}         → []
GET  /v2/articles?group=32433&limit=3                                       → 3 VT records
```

So 32433 is a real VT group, but it only works on the *list* endpoint, not on *search* —
and it is only one of many. Sampling 100 results for "Virginia Tech" and keeping those with
VT's `10.7294` DOI prefix gave 93 records spanning **23 distinct group_ids**:

```
33008: 50    31649: 10    32127: 4     32208: 4     32652: 4
31839: 2     32271: 2     32292: 2     32433: 1     ...15 more with 1 each
```

`32433` accounted for a single record. Filtering on it discards ~99% of VT content.

**Use instead:** the DOI prefix. Every VT Data Repository record carries a DOI under
`10.7294`, and it is stable, documented, and present in the search response.

```
POST /v2/articles/search  {"search_for": "...", "limit": 100}
  → keep records where doi startswith "10.7294"
```

### …and the DOI prefix does not rescue topical search

The prefix filter is correct, but it cannot fix a recall problem upstream of it. VT's corpus
is a rounding error inside global Figshare, and the public search index does not surface it:

```
POST search  {"search_for":"soil moisture","limit":25}                → 25 records, 0 VT
POST search  {"search_for":"soil moisture Virginia Tech","limit":25}  → 0 records
POST search  {"search_for":"soil moisture :group: 32433"}             → syntax ignored
POST search  {"search_for":"...","institution":1213}                  → []
GET  /v2/articles?group=32433&limit=100                               → 13 records, 13 VT
```

`"Virginia Tech"` alone does return VT records (93 of 100), so the index has them — the
terms simply AND together and no VT dataset matches all four. And the one call that works
cleanly, the group listing, cannot search and covers one of 23+ groups.

**Conclusion:** there is no working topical search over VT datasets through the public API.
Figshare stays in v0 for known-item lookups and browsing, and the system prompt tells the
agent not to promise dataset coverage. The fix is VT's Figshare **institution ID**, which
should make the `institution` filter work; that makes it a blocker for dataset discovery
rather than a nice-to-have. There is no public groups listing to enumerate from either —
`/v2/groups` and `/v2/account/institutions/groups` both 404.

---

## 2. Payload size is the real constraint

The survey treated auth and rate limits as the obstacles. Neither binds. Response size does,
because on NebulaONE every byte an endpoint returns enters the context window.

| Call | Measured | Note |
|---|---|---|
| DSpace `search/objects?size=2` | 44,005 B | two points give ~14 KB/item |
| DSpace `search/objects?size=5` | 86,290 B | over ~16 KB fixed facet/`_links` overhead |
| — one item's `indexableObject` | 8,141 B | the rest is `_links` wrappers and facet blocks |
| — one item's `metadata` | 6,482 B | of which the abstract is 2,322 B — the part you want |
| — `pubs.organisational-group` | 714 B | pure noise, unavoidable, no field selection in DSpace |
| OpenAlex `works`, raw | 41,548 B / 2 | ~20 KB per work |
| OpenAlex `works` + `select=` | 28,277 B / 5 | ~5.6 KB per work — **4× reduction** |
| Figshare `articles/search` | 25,503 B / 25 | ~1.0 KB per item, lean |

Fitting the two DSpace points: **~14 KB per item over ~16 KB of fixed overhead**, so
`size=10` extrapolates to roughly 157 KB. An earlier estimate here of "~8 KB/item" was wrong
— that was the `indexableObject` measured alone, excluding the `_links` envelope wrapped
around every object and the facet blocks beside them.

**Consequences baked into v0:** DSpace queries use `size=5`, not 10. OpenAlex always carries
`select=`. Dropping `authorships` from the select shrinks it further if you only need
citation-level detail.

DSpace has no field-projection parameter, so its waste is unavoidable without a proxy. It is
tolerable because the single fattest field is the abstract, which is genuinely wanted.

---

## 3. The full-text path is confirmed, and it is expensive

The survey's headline claim was right. Verified end to end:

```
GET /server/api/core/items/{uuid}/bundles          → LICENSE, ORIGINAL, TEXT, THUMBNAIL
GET /server/api/core/bundles/{TEXT-uuid}/bitstreams → *.pdf.txt + _links.content
GET /server/api/core/bitstreams/{uuid}/content     → text/plain; charset=UTF-8
```

Clean extracted text, no PDF parsing, no auth. Exactly as described.

**The part the survey did not quantify:** that chain is three round trips, and the payload
for one *journal article* was 100,395 B — 15,191 words. VTechWorks' distinctive holding is
ETDs, which are dissertations; those run several times larger.

With no filesystem and no chunking, a single ETD can consume an entire context window. Hence
the v0 rule: **one full-text read per conversation, abstracts otherwise.** Server-side
passage ranking is the main thing v1's proxy would buy, and the reason to build it is this
number, not Primo.

---

## 4. Primo `/pnxs` — the survey was right, and v0 was wrong to exclude it

Primo was initially left out of v0 on the grounds that its payload was too large without a
trimming proxy. That was asserted, not measured. Measured:

| `limit` | Bytes | |
|---|---|---|
| 1 | 21,096 | |
| 5 | **91,278** | ~17.5 KB/record |
| 10 | 172,063 | |

Compare DSpace at `size=5`: 86,290 B. **Primo costs essentially the same per search as a
source already shipping in v0**, so the exclusion failed on its own stated criterion. It is
in v0 as of this revision.

Everything the survey claimed holds. Unauthenticated `GET`, `info.total` 9,525 for
*machine learning soil moisture*, and the catalog variant
(`scope=MyInstitution&tab=LibraryCatalog`) returned 810 results for *soil physics*, typed
`book` — matching the survey's figure exactly. Per record: `pnx.addata.doi`,
`pnx.addata.issn`, `pnx.addata.abstract`, `pnx.display.oa`, `delivery.availability`
(`fulltext` / `fulltext_multiple`), and `delivery.almaOpenurl` for handoff.

**Where the bytes go**, per record: `pnx` 15,997 B and `delivery` 1,377 B, and within `pnx`,
`search` 4,129 B + `facets` 3,122 B + `control` 963 B are ~60% waste the agent never reads.
There is no field selector on `/pnxs`. This is the strongest argument for the v1 proxy —
stronger than anything about Primo's documentation status.

**Quirk:** titles are frequently duplicated in-field (`"Title: Title"`). Dedupe on display.

**The standing caveat is maintenance, not permission.** `/pnxs` is the Discovery UI's own
internal API — the identical request a browser makes, from VT patrons against VT's own
discovery layer, at conversation volume. It is a sound bridge. It is also uncontracted and
can change without notice, so a schema break is expected maintenance, and the supported
`/primo/v1/search` should replace it once a key exists.

## 5. Not yet verified

- **Unpaywall.** Requires an `email` parameter; not called during probing to avoid sending
  a personal address to a third party. `probe.sh --email you@vt.edu` exercises it. Use a
  `@vt.edu` address — it identifies the institution to Unpaywall's and OpenAlex's polite-use
  pools, which is both faster and better manners.
- **NebulaONE's response size cap.** Unknown, and it is the highest-value unknown remaining.
  See `probes/README.md`.
