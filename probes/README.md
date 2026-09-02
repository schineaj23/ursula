# Probes

```sh
./probe.sh                      # keyless sources
./probe.sh --email you@vt.edu   # also exercises Unpaywall
```

`probe.sh` calls every v0 endpoint and prints the payload size of each. Those sizes are the
design constraint — on NebulaONE, an endpoint's response goes straight into the agent's
context window — so re-run it after any endpoint change, and treat a size regression as a
real regression.

It also re-checks the two things
[`../reference/survey-corrections.md`](../reference/survey-corrections.md) asserts are
broken. If Figshare's `group` filter ever starts working, the probe fails loudly and the
corrections file needs revisiting.

---

## The size-cap test

**The highest-value unknown in this project.** NebulaONE's response size cap — where it
truncates an endpoint's output, if it does — determines whether Primo needs a hosted proxy
or is merely wasteful. Ten minutes to answer, and it should be answered before any
infrastructure is built.

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

What the answer implies:

- **≥ 500 KB** — Primo's raw `/pnxs` is registrable directly and the proxy is a token-cost
  optimization, not a requirement. Full-text reads of ETDs become viable, one at a time.
- **~100–500 KB** — matches what v0 already assumes. Keep the small `size`/`per-page`
  limits; one full-text read per conversation stands.
- **< 100 KB** — even a single VTechWorks full-text read is at risk, and server-side
  passage ranking moves from a v1 nicety to the thing that makes the agent work at all.
