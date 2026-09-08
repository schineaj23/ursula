"""Everything institution-specific, in one place."""

from __future__ import annotations

import os

PRIMO_PNXS = "https://virginiatech.primo.exlibrisgroup.com/primaws/rest/pub/pnxs"
PRIMO_VID = "01VT_INST:01VT_INST"
PRIMO_INST = "01VT_INST"

DSPACE = "https://vtechworks.lib.vt.edu/server/api"
DSPACE_HANDLE_PREFIX = "10919"

FIGSHARE = "https://api.figshare.com/v2"
VT_DOI_PREFIX = "10.7294"
"""The reliable VT Data Repository filter. `group_id` is not — see survey-corrections.md."""

OPENALEX = "https://api.openalex.org"

MAILTO = os.environ.get("URSULA_MAILTO", "")
"""A @vt.edu address puts OpenAlex calls in the polite pool. Set URSULA_MAILTO."""

TIMEOUT = float(os.environ.get("URSULA_TIMEOUT", "45"))
USER_AGENT = f"ursula/0.1 (VT University Libraries{'; ' + MAILTO if MAILTO else ''})"

MAX_TEXT_BYTES = int(os.environ.get("URSULA_MAX_TEXT_BYTES", str(8 * 1024 * 1024)))
"""Ceiling on a full text fetched into the *service*. Never enters an agent's context."""
