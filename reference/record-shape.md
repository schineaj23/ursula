# The normalized record

Four sources describe the same objects in four vocabularies. Everything downstream of a
search speaks one shape.

This document is the contract; [`../src/ursula/models.py`](../src/ursula/models.py) is the
implementation and [`../tests/test_sources.py`](../tests/test_sources.py) is what holds each
source to it. The conversion happens server-side, so an agent never sees a raw vocabulary.

```
Record
  title          string
  authors        string[]
  year           int
  type           "article" | "thesis" | "dataset" | "report" | "book" | "other"
  doi            string | null
  abstract       string | null
  source         "primo" | "vtechworks" | "vtdr" | "openalex"
  access_route   enum, see below
  text_uri       string | null     — where full text can actually be fetched
  cite_uri       string            — where a human should be sent
```

## `access_route`

The load-bearing field. An enum, never a boolean, because "can I read this" has five
different answers with five different follow-up actions.

| Value | Meaning | Agent's move |
|---|---|---|
| `vtechworks_text` | DSpace `TEXT` bundle exists and is non-empty | Fetch it. Clean UTF-8, no parsing. |
| `figshare_file` | Public Figshare `download_url` | Fetch if textual (CSV, README, docs). |
| `oa_pdf` | Unpaywall/OpenAlex found a legal OA copy | Offer the link. Fetching costs a PDF parse the agent doesn't have. |
| `abstract_only` | Metadata retrieved, no full text located | Say so explicitly. Do not imply more. |
| `licensed_handoff` | Behind a VT subscription | Give the link, stop, offer ILLiad. |

The agent must never state or imply it has read something whose route is `abstract_only`
or `licensed_handoff`. This is the difference between a tool the library will endorse and
one it will not.

## Field mapping

| Normalized | Primo (PNX) | VTechWorks (Dublin Core) | Figshare | OpenAlex |
|---|---|---|---|---|
| `title` | `pnx.display.title[0]` ¶ | `metadata["dc.title"][0].value` | `title` | `title` |
| `authors` | `pnx.display.creator[]` | `metadata["dc.contributor.author"][].value` | `authors[].full_name` † | `authorships[].author.display_name` |
| `year` | `pnx.display.creationdate[0]` | `metadata["dc.date.issued"][0].value` | `published_date` | `publication_year` |
| `type` | `pnx.display.type[0]` | `metadata["dc.type"][0].value` | `defined_type_name` | `type` |
| `doi` | `pnx.addata.doi[0]` | `metadata["dc.identifier.doi"][0].value` | `doi` | `doi` |
| `abstract` | `pnx.addata.abstract[0]` | `metadata["dc.description.abstract"][0].value` | `description` † | `abstract_inverted_index` ‡ |
| `cite_uri` | `delivery.almaOpenurl` | `https://hdl.handle.net/{handle}` | `url_public_html` † | `primary_location.landing_page_url` |

† Only on the detail endpoint `GET /v2/articles/{id}`, not in search results.
‡ OpenAlex returns abstracts as a word-to-positions inverted index. `sources/openalex.py`
rebuilds it, which costs nothing server-side and would be absurd to ask a model to do.
¶ Primo titles are frequently duplicated in-field (`"Title: Title"`). Dedupe before display.

## Deriving `access_route` from Primo

Primo does not state an access route directly; you infer it from two fields.

| Signal | Route |
|---|---|
| `pnx.display.oa` present | `oa_pdf` — confirm the location via OpenAlex |
| `delivery.availability` contains `fulltext` / `fulltext_multiple` | `licensed_handoff` — VT has it, you do not |
| `pnx.display.type == "book"`, catalog scope | `licensed_handoff`, physical — cite `delivery.holding` |
| no availability signal | `abstract_only` |

`fulltext` here means *VT users can reach the full text after signing in*, not that you can.
Reading it as "I have the full text" is the single worst mistake available in this system.

## Merging

The same paper legitimately appears twice — once in OpenAlex as the published version, once
in VTechWorks as VT's accepted manuscript. That is not a duplicate to suppress; it is the
open copy of a closed article, and it is the most valuable pattern in the whole system.

1. Match on DOI when both have one. Fall back to normalized title (lowercase, strip
   punctuation and articles) plus year within ±1.
2. Keep the richest metadata across the pair.
3. **Prefer the `access_route` that yields text.** `vtechworks_text` beats `oa_pdf` beats
   `abstract_only` beats `licensed_handoff`.
4. Cite the published version, read the VT copy, and say that is what you did.

Step 4 is the behaviour worth getting right. "This is Elsevier-published and paywalled, but
VT deposited the accepted manuscript and I read that" is exactly what a research library
wants its agent to do.
