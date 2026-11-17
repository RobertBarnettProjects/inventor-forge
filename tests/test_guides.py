"""Offline tests for the reference guides: the guide tool, MCP resources, and that every tool a guide names exists.

    python -m pytest tests/test_guides.py
"""
import json
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge import guides  # noqa: E402
from inventor_forge.com import InventorError  # noqa: E402
from inventor_forge.registry import TOOLS, load_all  # noqa: E402

load_all()


def test_every_topic_reads_and_is_short():
    for t in guides.topics():
        text = guides.read(t)
        assert text.startswith("# ") and len(text) < 8000, t
    assert guides.read("fea") == guides.read("stress-analysis")


def test_guide_tool():
    g = TOOLS["guide"].fn
    assert "drawings" in g(None)["topics"]
    assert "Superseded" in g(None, topic="drawings")["text"]
    with pytest.raises(InventorError, match="topics"):
        g(None, topic="nope")


def test_tools_named_in_guides_exist():
    known = set(TOOLS) | {k for t in TOOLS.values() for k in t.schema["properties"]}
    for t in guides.topics():
        for name in re.findall(r"`([a-z_]+)(?:\(|`)", guides.read(t)):
            if "_" in name and name not in ("sa_n", "typed_call"):
                assert name in known, (t, name)


def test_guides_are_mcp_resources():
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "resources/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "resources/read",
             "params": {"uri": "inventor-forge://guide/session"}},
            {"jsonrpc": "2.0", "id": 4, "method": "resources/read", "params": {"uri": "inventor-forge://guide/x"}}]
    p = subprocess.run([sys.executable, "-X", "utf8", "-m", "inventor_forge.server"],
                       input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True,
                       cwd=os.path.join(os.path.dirname(__file__), ".."), timeout=60, encoding="utf-8")
    rep = {r["id"]: r for r in (json.loads(x) for x in p.stdout.splitlines() if x.strip())}
    assert "resources" in rep[1]["result"]["capabilities"]
    uris = [r["uri"] for r in rep[2]["result"]["resources"]]
    assert "inventor-forge://guide/stress-analysis" in uris
    assert rep[3]["result"]["contents"][0]["text"].startswith("# Session")
    assert rep[4]["error"]["code"] == -32602


def test_targeted_hints():
    from inventor_forge.hints import hint_for
    assert "VT_BSTR" in hint_for("set_sheet_format", "E_INVALIDARG")
    assert "surface" in hint_for("split_faces", "Exception occurred")
    assert "export_print_package" in hint_for("export_document", "3MF export failed")
