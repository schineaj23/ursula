#!/usr/bin/env bash
# Smoke-test every v0 endpoint and report measured payload sizes.
#
#   ./probes/probe.sh                      # keyless sources only
#   ./probes/probe.sh --email you@vt.edu   # also exercises Unpaywall
#
# Sizes here are what NebulaONE would put in the agent's context window, so they are the
# number that matters. Re-run after any endpoint change.

set -uo pipefail

EMAIL=""
[[ "${1:-}" == "--email" ]] && EMAIL="${2:-}"

OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

DSPACE="https://vtechworks.lib.vt.edu/server/api"
Q="soil moisture machine learning"
pass=0 fail=0

hr()   { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$*"; fail=$((fail+1)); }
note() { printf '    %s\n' "$*"; }

# get <name> <file> <curl-args...>
get() {
  local name="$1" file="$2"; shift 2
  local code size
  IFS=' ' read -r code size < <(curl -sS -m 45 -w '%{http_code} %{size_download}' \
    -o "$OUT/$file" "$@" 2>/dev/null || echo "000 0")
  if [[ "$code" == "200" ]]; then
    ok "$name — ${size} B"
  else
    bad "$name — HTTP $code"
  fi
  [[ "$code" == "200" ]]
}

hr "0 · Primo VE discovery (undocumented /pnxs)"
PNXS="https://virginiatech.primo.exlibrisgroup.com/primaws/rest/pub/pnxs"
primo() { # primo <label> <file> <scope> <tab> <query> <limit>
  get "$1" "$2" --get "$PNXS" \
    -d "vid=01VT_INST:01VT_INST" -d "inst=01VT_INST" -d "lang=en" \
    --data-urlencode "q=any,contains,$5" \
    -d "scope=$3" -d "tab=$4" -d "offset=0" -d "limit=$6" \
    -d "sort=rank" -d "pcAvailability=true"
}
if primo "central index, limit=5" pnx.json MyInst_and_CI Everything "$Q" 5; then
  note "total: $(jq -r '.info.total // "?"' "$OUT/pnx.json")  docs: $(jq '.docs|length' "$OUT/pnx.json")"
  note "doi/oa/openurl present: $(jq -r '[
      (.docs[0].pnx.addata.doi[0]//"–"),
      (.docs[0].pnx.display.oa|tostring),
      (if .docs[0].delivery.almaOpenurl then "openurl" else "–" end)] | join(" · ")' "$OUT/pnx.json")"
fi
if primo "catalog scope, limit=3" pnx_book.json MyInstitution LibraryCatalog "soil physics" 3; then
  note "types: $(jq -r '[.docs[].pnx.display.type[0]] | unique | join(", ")' "$OUT/pnx_book.json")"
fi

hr "1 · VTechWorks search (DSpace 7.6.1)"
if get "search/objects?size=5" dspace.json \
     --get "$DSPACE/discover/search/objects" \
     --data-urlencode "query=$Q" -d "dsoType=item" -d "size=5"; then
  n=$(jq '._embedded.searchResult._embedded.objects | length' "$OUT/dspace.json" 2>/dev/null)
  note "items: ${n:-?}"
  jq -r '._embedded.searchResult._embedded.objects[0]._embedded.indexableObject.name' \
    "$OUT/dspace.json" 2>/dev/null | cut -c1-70 | sed 's/^/    first: /'
fi

hr "2 · VTechWorks full-text chain (3 hops)"
UUID=$(jq -r '._embedded.searchResult._embedded.objects[0]._embedded.indexableObject.uuid' \
  "$OUT/dspace.json" 2>/dev/null)
if [[ -n "${UUID:-}" && "$UUID" != "null" ]]; then
  if get "items/$UUID/bundles" bundles.json "$DSPACE/core/items/$UUID/bundles"; then
    note "bundles: $(jq -r '[._embedded.bundles[].name] | join(", ")' "$OUT/bundles.json")"
    BUNDLE=$(jq -r '._embedded.bundles[] | select(.name=="TEXT") | .uuid' "$OUT/bundles.json")
    if [[ -n "${BUNDLE:-}" ]]; then
      if get "bundles/$BUNDLE/bitstreams" bits.json "$DSPACE/core/bundles/$BUNDLE/bitstreams"; then
        BS=$(jq -r '._embedded.bitstreams[0]._links.content.href' "$OUT/bits.json")
        SZ=$(jq -r '._embedded.bitstreams[0].sizeBytes' "$OUT/bits.json")
        note "TEXT bitstream declares ${SZ} B"
        if get "bitstream content" full.txt "$BS"; then
          note "words: $(wc -w < "$OUT/full.txt" | tr -d ' ') — this is one context spend"
        fi
      fi
    else
      bad "no TEXT bundle on this item (abstract-only)"
    fi
  fi
else
  bad "no uuid from search — skipping full-text chain"
fi

hr "3 · Figshare / VT Data Repository"
if get "POST articles/search" fig.json \
     -X POST "https://api.figshare.com/v2/articles/search" \
     -H "Content-Type: application/json" \
     -d '{"search_for":"soil moisture","limit":25}'; then
  tot=$(jq 'length' "$OUT/fig.json")
  vt=$(jq '[.[] | select(.doi // "" | startswith("10.7294"))] | length' "$OUT/fig.json")
  note "returned $tot, VT (doi 10.7294) $vt"
  [[ "$vt" == "0" ]] && note "0 VT hits is normal for a generic term — see reference/survey-corrections.md"
fi
# The filter the prior survey recommended. Asserted broken; verify it stays broken.
g=$(curl -sS -m 30 -X POST "https://api.figshare.com/v2/articles/search" \
      -H "Content-Type: application/json" \
      -d '{"search_for":"soil moisture","group":32433,"limit":5}' 2>/dev/null | jq 'length' 2>/dev/null)
if [[ "$g" == "0" ]]; then
  ok "group:32433 search filter still returns [] (expected — use the DOI prefix)"
else
  bad "group:32433 now returns $g — Figshare changed; revisit the corrections file"
fi

hr "4 · OpenAlex"
SEL="id,doi,title,publication_year,type,open_access,primary_location,authorships"
get "works (raw, 2)" oa_raw.json \
  --get "https://api.openalex.org/works" --data-urlencode "search=$Q" -d "per-page=2"
if get "works (select=, 5)" oa_sel.json \
     --get "https://api.openalex.org/works" --data-urlencode "search=$Q" \
     -d "per-page=5" -d "select=$SEL" ${EMAIL:+-d "mailto=$EMAIL"}; then
  note "select= is a ~4x reduction per work — always send it"
fi

hr "5 · Unpaywall"
if [[ -z "$EMAIL" ]]; then
  note "skipped — re-run with --email you@vt.edu"
else
  DOI=$(jq -r '.results[0].doi // ""' "$OUT/oa_sel.json" | sed 's|https://doi.org/||')
  if [[ -n "$DOI" ]]; then
    get "v2/$DOI" up.json "https://api.unpaywall.org/v2/$DOI?email=$EMAIL" \
      && note "is_oa: $(jq -r '.is_oa' "$OUT/up.json")"
  else
    bad "no DOI available from OpenAlex to resolve"
  fi
fi

hr "Result"
printf '  %d passed, %d failed\n\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
