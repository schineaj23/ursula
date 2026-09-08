# Upstream APIs

What the four sources actually return, and what each call costs. Sizes are measured, not
estimated; see [`survey-corrections.md`](survey-corrections.md).

> **These are no longer registered with any agent.** `src/ursula/sources/` calls them, and
> [`../agent/endpoints.md`](../agent/endpoints.md) is what a host registers instead. This
> file is the reference behind that code: the field paths, the traps, and the payload
> measurements that argued for putting a service in front of all of it. The JSON Schema
> blocks below are kept as a record of the direct-registration design that preceded it.
>
> Five of the ten endpoints below cannot be registered in NebulaONE at all, because it
> accepts only `?param=value` URLs and they take a path segment. That constraint is what
> the service exists to absorb.

## Two conventions from the direct-registration design

**Only values the model should choose are parameters.** `vid`, `inst`, `scope`, `tab`,
`limit`, `size`, `per-page`, `select` and `sort` are all baked into the registered URL, not
exposed in the schema. The model cannot then widen a scope it shouldn't, or raise a limit
past the context budget — the budget is enforced by registration, not by asking the prompt
nicely. Pagination (`offset`) is deliberately omitted in v0 for the same reason; add it only
once the size cap is known.

**Parameter descriptions are prompt surface.** The model reads them at call time, so each
one carries its routing hint and its traps. The `uuid` descriptions are what teach the
three-hop full-text chain — that sequence is learned from the schemas, not from the system
prompt.

---

## 1 · `primo_search` — the licensed and central index

Everything VT can get at: journal articles, ebooks, conference papers, across the Ex Libris
central index plus VT holdings. **Broadest coverage of any source here.**

```
GET https://virginiatech.primo.exlibrisgroup.com/primaws/rest/pub/pnxs
      ?vid=01VT_INST:01VT_INST&inst=01VT_INST&lang=en
      &q=any,contains,{query}
      &scope=MyInst_and_CI&tab=Everything
      &offset=0&limit=5&sort=rank&pcAvailability=true
```

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "The research topic to search for, as plain keywords — for example 'machine learning soil moisture'. Do not use boolean operators, quotation marks, or field prefixes; the endpoint applies 'any,contains' matching across all fields and treats operators as literal search terms. Three to six substantive nouns works best. Full sentences and question phrasing reduce recall sharply, so strip words like 'how does' and 'what is' before calling."
    }
  },
  "required": ["query"]
}
```

Records are at `docs[]`. Per record:

| Need | Path |
|---|---|
| title | `pnx.display.title[0]` |
| authors | `pnx.display.creator[]` |
| type | `pnx.display.type[0]` |
| DOI | `pnx.addata.doi[0]` |
| ISSN | `pnx.addata.issn[0]` |
| abstract | `pnx.addata.abstract[0]` |
| open access flag | `pnx.display.oa` |
| access signal | `delivery.availability[]` — `fulltext`, `fulltext_multiple` |
| **handoff link** | `delivery.almaOpenurl` |

> **`limit=5` is the ceiling** — measured at 91 KB (~17.5 KB/record; `limit=10` is 172 KB).
> About 60% of each record is `pnx.search`, `pnx.facets` and `pnx.control`, none of which
> the agent needs, and `/pnxs` has no field selector. This is the single biggest argument
> for the v1 proxy.
>
> **Titles are frequently duplicated** in this field (`"Title: Title"`). Dedupe on display.

> ⚠️ **Undocumented endpoint.** This is the Discovery UI's own internal API, not a
> contracted one — the same request your browser makes. It works, it needs no key, and it
> is a reasonable bridge until an Ex Libris Developer Network key is issued. It can also
> change without notice, so treat a schema break here as expected maintenance rather than a
> surprise, and swap to the supported `/primo/v1/search` once a key exists.

## 2 · `primo_catalog` — VT's own books and physical holdings

Same endpoint, narrowed scope. Use for textbooks, "does the library have X", physical items.

```
GET https://virginiatech.primo.exlibrisgroup.com/primaws/rest/pub/pnxs
      ?vid=01VT_INST:01VT_INST&inst=01VT_INST&lang=en
      &q=any,contains,{query}
      &scope=MyInstitution&tab=LibraryCatalog
      &offset=0&limit=5&sort=rank&pcAvailability=true
```

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "A book title, author, or subject to look for in Virginia Tech's own catalog — for example 'soil physics' or 'Hillel introduction to environmental soil physics'. Plain keywords only, no boolean operators. This searches VT's holdings rather than the global index, so it answers 'does the library have this' and 'what books do we own on this subject'. For journal articles use primo_search instead."
    }
  },
  "required": ["query"]
}
```

Verified: "soil physics" → 810 results, typed `book`, ~26 KB at `limit=3`. Physical
availability is under `delivery.holding` and `delivery.displayLocation`.

## 3 · `vtechworks_search` — VT's own output, and the only readable full text

VT theses, dissertations, preprints, accepted manuscripts. **Start here whenever reading
the document matters.**

```
GET https://vtechworks.lib.vt.edu/server/api/discover/search/objects
      ?query={query}&dsoType=item&size=5
```

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Keywords to search Virginia Tech's institutional repository — theses, dissertations, faculty preprints, accepted manuscripts and technical reports. Plain terms work best; this is a Solr index, so it also accepts field syntax like 'author:Smith' or quoted phrases when you need precision. This is the only source whose full text can actually be read, so search it whenever the user wants a document analyzed rather than just located."
    }
  },
  "required": ["query"]
}
```

Records live at:

```
_embedded.searchResult._embedded.objects[]._embedded.indexableObject
```

with `uuid`, `handle`, `name`, and a `metadata` object keyed by Dublin Core field names
(`dc.title`, `dc.contributor.author`, `dc.description.abstract`, `dc.identifier.doi`,
`dc.date.issued`), each a list of `{value, language, place}`.

> **Keep `size=5`** — measured at 86 KB. Roughly 14 KB per item over 16 KB of fixed facet
> and `_links` overhead, so `size=10` runs to ~157 KB. DSpace has no field-selection
> parameter; the waste is structural.

## 4 · `vtechworks_bundles` — full text, hop 1 of 3

```
GET https://vtechworks.lib.vt.edu/server/api/core/items/{itemUuid}/bundles
```

```json
{
  "type": "object",
  "properties": {
    "itemUuid": {
      "type": "string",
      "description": "The 'uuid' field of a VTechWorks item, taken from a vtechworks_search response at _embedded.searchResult._embedded.objects[]._embedded.indexableObject.uuid. This is hop 1 of 3 in the full-text chain: call this to list the item's bundles, look for the one named TEXT, then pass that bundle's uuid to vtechworks_bitstreams. If no bundle is named TEXT, the item has no extracted text and is abstract-only — stop there and say so."
    }
  },
  "required": ["itemUuid"]
}
```

Returns `_embedded.bundles[]`. Look for `name == "TEXT"` and take its `uuid`. Its absence
means no extracted text — the item is `abstract_only`.

## 5 · `vtechworks_bitstreams` — hop 2

```
GET https://vtechworks.lib.vt.edu/server/api/core/bundles/{bundleUuid}/bitstreams
```

```json
{
  "type": "object",
  "properties": {
    "bundleUuid": {
      "type": "string",
      "description": "The 'uuid' of the bundle named TEXT, from a vtechworks_bundles response. This is hop 2 of 3. The response lists bitstreams; take the first one's 'sizeBytes' and check it before going further, because the next call spends that many bytes of context. A journal article runs about 100 KB; a dissertation can run several times more."
    }
  },
  "required": ["bundleUuid"]
}
```

Returns `_embedded.bitstreams[]`. Take `_links.content.href` — and read `sizeBytes` first,
because it tells you what you are about to spend.

## 6 · `vtechworks_fulltext` — hop 3

```
GET https://vtechworks.lib.vt.edu/server/api/core/bitstreams/{bitstreamUuid}/content
```

```json
{
  "type": "object",
  "properties": {
    "bitstreamUuid": {
      "type": "string",
      "description": "The uuid of the TEXT bitstream, from a vtechworks_bitstreams response — it is the last path segment of _embedded.bitstreams[0]._links.content.href. This is hop 3 of 3 and returns the document's entire plain text in one response. It is by far the most expensive call available to you: budget one per conversation, and only after the abstract has proved insufficient."
    }
  },
  "required": ["bitstreamUuid"]
}
```

Returns `text/plain; charset=UTF-8`. Clean extracted text, no PDF parsing.

> **The expensive call.** A journal article measured 100 KB / 15,191 words. ETDs are
> dissertations and run several times that. One per conversation.

## 7 · `figshare_search`

VT datasets and supplementary research products.

```
POST https://api.figshare.com/v2/articles/search
Content-Type: application/json

{"search_for": "{searchFor}", "limit": 25}
```

```json
{
  "type": "object",
  "properties": {
    "searchFor": {
      "type": "string",
      "description": "Keywords describing the dataset being looked for, such as 'soil moisture sensor calibration'. This searches all of Figshare globally, not just Virginia Tech, so you must keep only results whose 'doi' begins with '10.7294' — those are VT's. Ignore 'group_id'; it does not identify VT. Recall for VT material is poor, so treat an empty result as 'I could not find it', never as 'VT has no such data'."
    }
  },
  "required": ["searchFor"]
}
```

Returns a flat array — no envelope, ~1.0 KB per item.

> **Filter on the DOI prefix `10.7294`, not on `group_id`.** VT records span 23+ group ids;
> the `group` and `institution` body filters both return empty.
>
> **Expect low recall.** Global Figshare search does not surface VT's small corpus for
> topical queries — `"soil moisture"` at `limit=25` returned zero VT records. This endpoint
> is for known-item lookups, not dataset discovery. Getting VT's institution ID from Data
> Services is what fixes it. See the corrections file.

## 8 · `figshare_detail`

Search results omit `description`, `authors`, and `files`. For a specific record:

```
GET https://api.figshare.com/v2/articles/{articleId}
```

```json
{
  "type": "object",
  "properties": {
    "articleId": {
      "type": "integer",
      "description": "The numeric 'id' of a Figshare record from a figshare_search result — for example 33415639. Not the DOI. Call this only for a record you have already decided is relevant, since it is the only way to get the description, author list, and files[].download_url, none of which appear in search results."
    }
  },
  "required": ["articleId"]
}
```

`files[].download_url` is unauthenticated for public items.

## 9 · `openalex_search`

Scholarly metadata worldwide, with reliable open-access status. Complements Primo — Primo
knows what VT licenses, OpenAlex knows what is freely readable.

```
GET https://api.openalex.org/works
      ?search={search}&per-page=5&mailto=you@vt.edu
      &select=id,doi,title,publication_year,type,open_access,primary_location,authorships
```

```json
{
  "type": "object",
  "properties": {
    "search": {
      "type": "string",
      "description": "Keywords, or an exact article title when checking a specific paper. Searches titles, abstracts and full text across the global scholarly literature. Use this to find a legally readable open-access copy of something primo_search surfaced behind a subscription: check 'open_access.oa_status' and 'open_access.oa_url' on each result. Note that the 'doi' field comes back as a full URL like 'https://doi.org/10.1234/xyz'."
    }
  },
  "required": ["search"]
}
```

> **`select=` is mandatory, not an optimization.** Without it a work is ~20 KB; with it,
> ~5.6 KB. Drop `authorships` too if you only need citation-level detail.

`open_access.oa_status` and `open_access.oa_url` often make a separate Unpaywall call
unnecessary.

## 10 · `unpaywall_resolve` ⚠️ not yet verified

```
GET https://api.unpaywall.org/v2/{doi}?email=you@vt.edu
```

```json
{
  "type": "object",
  "properties": {
    "doi": {
      "type": "string",
      "description": "A bare DOI such as '10.1007/s11269-024-04069-3'. Strip any 'https://doi.org/' prefix before calling — OpenAlex returns DOIs in full-URL form and this endpoint returns 404 for them. Only call this when OpenAlex's open_access block was missing or inconclusive for the same DOI; otherwise it is a second round trip for a fact you already have."
    }
  },
  "required": ["doi"]
}
```

`best_oa_location.url_for_pdf` is the legal OA copy when one exists. The `email` parameter
is required by Unpaywall.

Run `./probes/probe.sh --email you@vt.edu` before relying on this one.
