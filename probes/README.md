# Probes

Endpoint smoke-testing now lives in the test suite:

```sh
pytest              # offline: parsers, merging, ranking, the HTTP contract
pytest --live       # also calls Primo, VTechWorks, Figshare and OpenAlex for real
```

`pytest --live` replaced `probe.sh`. It asserts the same upstream shapes and keeps the same
regression guards, including the check that Figshare's `group` filter is still broken. A
schema change upstream now shows up as a named failing test rather than an empty result set.

---

## The size-cap test

Less urgent than it was — the service keeps every response small, so a search is ~17 KB and
a document read ~4 KB rather than the 90–100 KB the raw APIs return. It is still worth
knowing, because it bounds how large a `limit` or `max_chars` an agent can usefully ask for.

It cannot be tested from here; it is a property of the platform, not the APIs. Run it inside
NebulaONE:

1. Register one throwaway endpoint with a deliberately large response:

   ```
   GET https://vtechworks.lib.vt.edu/server/api/discover/search/objects
         ?query=soil&dsoType=item&size=100
   ```

   That is on the order of 800 KB.

2. Ask the agent: *"How many items did that return, and what is the title of the last
   one?"*

3. A correct answer means nothing truncated at that size. A short count, a complaint about
   malformed JSON, or a confabulated title means you found the ceiling.

4. Bisect on `size` until it answers reliably. Record the number here.

**Findings:**

| Date | `size` | Bytes | Result |
|---|---|---|---|
| _pending_ | | | |

What the answer implies now that the service exists:

- **≥ 200 KB** — the defaults are comfortable, and `max_chars` can go to 40,000 for a
  synthesis across a long document.
- **~50–200 KB** — the defaults are right as they stand. No change.
- **< 50 KB** — lower the default `limit` and `abstract_chars`, and read documents in
  smaller passages.
