import json
import re
from pathlib import Path

import pytest

DOC = (Path(__file__).resolve().parents[1] / "agent" / "endpoints.md").read_text()
MAX_DESCRIPTION_CHARS = 1024

#: (stated length, description text) for each endpoint, in document order.
DESCRIPTIONS = [
    (
        int(n),
        "\n".join(
            line[2:] if line.startswith("> ") else ""
            for line in body.strip().split("\n")
        ),
    )
    for n, body in re.findall(
        r"\*\*Description\*\* \((\d+) characters\):\n\n((?:>.*\n)+)", DOC
    )
]

SCHEMAS = [json.loads(b) for b in re.findall(r"```json\n(.*?)\n```", DOC, re.DOTALL)]


def test_the_doc_documents_three_endpoints_with_a_description_each():
    assert len(SCHEMAS) == 3
    assert len(DESCRIPTIONS) == 3


@pytest.mark.parametrize("stated,text", DESCRIPTIONS)
def test_each_endpoint_description_fits_the_platform_cap(stated, text):
    assert len(text) <= MAX_DESCRIPTION_CHARS


@pytest.mark.parametrize("stated,text", DESCRIPTIONS)
def test_the_stated_character_count_is_accurate(stated, text):
    """The count is in the doc so an editor can see the headroom without measuring."""
    assert stated == len(text)


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda s: ",".join(s["properties"]))
def test_every_parameter_carries_its_own_guidance(schema):
    """No cap applies here, so parameter-specific detail belongs in the schema."""
    for name, prop in schema["properties"].items():
        assert prop.get("description"), f"{name} has no description"
        assert prop["type"] in ("string", "integer", "boolean")
    assert schema["required"]
