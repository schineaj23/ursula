# Registering Ursula

Three endpoints, whatever the host. They are the same three functions everywhere: an HTTP
service for NebulaONE and Open WebUI, an MCP server for locally run agents, a CLI for a
skill in a host that can execute code.

The upstream sources are no longer registered anywhere. Ursula calls them; see
[`../reference/upstream-apis.md`](../reference/upstream-apis.md) for what they return and
what each one costs.

## Why three, and why GET

Every operation is a `GET` with flat query parameters, because NebulaONE can register
`http://host/path?param=value` and nothing else. Rather than a limitation to route around,
that is the lowest common denominator every host can call, which is the shape a
provider-agnostic API wants anyway.

The parameter descriptions below are prompt surface. A model reads them at call time, so
each carries its routing hint and its traps, and they are worth editing with the same care
as the system prompt.

---

## 1 · `/search` — find things across all four sources at once

```
GET https://<host>/search?query={query}&sources={sources}&limit=5
```

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "The research topic to search for, as plain keywords — for example 'machine learning soil moisture'. Do not use boolean operators, quotation marks, or field prefixes; the upstream indexes treat them as literal search terms. Three to six substantive nouns works best. Full sentences and question phrasing reduce recall sharply, so strip words like 'how does' and 'what is' before calling."
    },
    "sources": {
      "type": "string",
      "description": "Comma-separated list of sources to search, or omit for the default of primo, vtechworks and openalex together. 'primo' is the library's discovery layer and has by far the broadest coverage, but you will rarely be able to read what it finds. 'vtechworks' is VT's institutional repository and the only source whose full text can actually be read, so include it whenever reading the document matters. 'openalex' finds legal open-access copies of paywalled work. 'vtdr' is VT's data repository, for datasets rather than prose. 'primo_catalog' is VT's own books and physical holdings, for 'does the library have X'."
    },
    "limit": {
      "type": "integer",
      "description": "Results requested from each source before merging, between 1 and 20. Five is the default and is usually right. Raising it widens coverage and lengthens the response proportionally; the merged set is normally smaller than sources times limit, because the same work found twice becomes one record.",
      "default": 5
    }
  },
  "required": ["query"]
}
```

Returns `records[]`, already merged and normalized, readable ones first. Roughly 17 KB for
fifteen records against the ~205 KB the same four searches cost unmerged.

| Field | Meaning |
|---|---|
| `id` | Pass to `/read` verbatim. Namespaced, e.g. `vtechworks:<uuid>` |
| `access_route` | One of `vtechworks_text`, `figshare_file`, `oa_pdf`, `abstract_only`, `licensed_handoff` |
| `readable` | True only when `/read` can return real text |
| `also_in` | Other sources holding the same work — usually the deposited-manuscript pattern |
| `cite_uri` | Where to send a human. For Primo this is the VT link resolver |
| `oa_url` | A legal open copy, when one exists |

`notes[]` carries anything the caller should say out loud, such as Figshare's recall
problem or a source that failed.

## 2 · `/read` — full text, reduced to what answers the question

```
GET https://<host>/read?id={id}&question={question}&max_chars=6000
```

```json
{
  "type": "object",
  "properties": {
    "id": {
      "type": "string",
      "description": "A record id exactly as it appeared in a /search response, such as 'vtechworks:b716bd09-0c7b-4c06-b582-4301b27cf5fe'. Only records marked 'readable': true have retrievable text; calling this on anything else returns guidance on what to do instead, not an error."
    },
    "question": {
      "type": "string",
      "description": "What you want to learn from this document, phrased in the user's own terms — for example 'what accuracy did the model achieve and on what data'. Passages are ranked against this, so a specific question returns a far better excerpt than a bare topic. Omit it and you get the document's opening instead, which is rarely what you want."
    },
    "max_chars": {
      "type": "integer",
      "description": "Ceiling on the characters of document text returned, between 200 and 40000. The default of 6000 is a few pages and answers most questions. Raise it for a synthesis across a whole argument; lower it when reading several documents in one conversation.",
      "default": 6000
    }
  },
  "required": ["id"]
}
```

Returns `passages[]` in document order, plus `chars_total` and `chars_returned` so the
caller knows how much of the document it did not see. `text_available: false` comes with
`guidance` naming the correct next move.

> **This endpoint is the reason the service exists.** One VTechWorks article's extracted
> text is 100 KB, which an agent can afford once. Ranked to 4 KB, it can afford it twenty
> times, and the one-document-per-conversation ceiling disappears.

## 3 · `/resolve` — DOI to open-access status

```
GET https://<host>/resolve?doi={doi}
```

```json
{
  "type": "object",
  "properties": {
    "doi": {
      "type": "string",
      "description": "A DOI, either bare like '10.1007/s11269-024-04069-3' or as a full 'https://doi.org/...' URL — both are accepted, so no stripping is needed. Call this on anything the discovery layer surfaced behind a subscription, before telling the user they cannot read it. Returns 'oa_url' when a legal open copy exists."
    }
  },
  "required": ["doi"]
}
```

About 2 KB. Backed by OpenAlex, which is why Unpaywall is no longer a dependency: the same
fact, one call, and no path segment NebulaONE cannot register.

---

## Registering it

**NebulaONE.** Register the three URLs above against the deployed host. No API key, no
headers. Paste [`system-prompt.md`](system-prompt.md) as the agent's prompt.

**Open WebUI.** Add the service as an OpenAPI tool server. It reads
`https://<host>/openapi.json` and generates all three tools with the descriptions above,
so there is nothing to type twice.

**Claude Code, prime-agent, Claude Desktop, Cursor.** Run the MCP server instead. Same
three functions, same record shape:

```jsonc
{
  "mcpServers": {
    "ursula": { "command": "ursula-mcp" }
  }
}
```

`ursula-mcp --http --port 8001` serves streamable HTTP for hosts that prefer it.

**A skill, or anything that can run a shell.** `ursula search "…"` and
`ursula read <id> --question "…"` print the same JSON. A host with a filesystem could of
course call VTechWorks directly and grep the result, but it would then have to re-derive
VT's routing rules and the access-route contract, which is exactly what this keeps in one
place.
