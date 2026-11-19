"""A client's write scope ("cad/write_scope") is enforced where files are written: final names, links followed,
dependent saves included, and a refusal names every path concerned before anything is written."""
import json
import os
from types import SimpleNamespace

import pytest

from inventor_forge import writes
from inventor_forge.tools import docs


@pytest.fixture
def scope(tmp_path, monkeypatch):
    # forge's own temporary files are always allowed; pytest's tmp_path lives there, so point "temp" elsewhere
    monkeypatch.setattr(writes.tempfile, "gettempdir", lambda: str(tmp_path / "forge-temp"))
    job = tmp_path / "job"
    job.mkdir()
    mark = writes.use_scope({"dirs": [str(job)], "files": [str(tmp_path / "approved.ipt")]})
    yield job
    writes.reset_scope(mark)


def _needed(err) -> list[str]:
    text = str(err)
    return json.loads(text.split(writes.NEEDS_MARK, 1)[1])


def test_inside_the_job_and_approved_files_pass(scope, tmp_path):
    writes.guard(str(scope / "a" / "part.ipt"))
    writes.guard(str(tmp_path / "approved.ipt"))
    writes.output_path(str(scope), "bracket", "exports", ".pdf")      # the final name (extension added) is checked


def test_outside_is_refused_and_named(scope, tmp_path):
    with pytest.raises(writes.NeedsApproval) as e:
        writes.guard(str(tmp_path / "elsewhere.ipt"))
    assert _needed(e.value) == [os.path.realpath(tmp_path / "elsewhere.ipt")]


def test_a_link_out_of_the_job_is_followed(scope, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        os.symlink(outside, scope / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need extra rights here")
    with pytest.raises(writes.NeedsApproval):
        writes.guard(str(scope / "link" / "x.ipt"))


def test_dependent_saves_are_checked_together(scope, tmp_path):
    a, b = tmp_path / "lib" / "a.ipt", tmp_path / "lib" / "b.ipt"
    refs = [SimpleNamespace(Dirty=True, FullFileName=str(a)), SimpleNamespace(Dirty=False, FullFileName=str(tmp_path / "c.ipt")),
            SimpleNamespace(Dirty=True, FullFileName=str(scope / "ok.ipt")), SimpleNamespace(Dirty=True, FullFileName=str(b))]

    class Refs(list):
        Count = property(len)

        def Item(self, i):
            return self[i - 1]
    with pytest.raises(writes.NeedsApproval) as e:
        docs._guard_dependents(SimpleNamespace(AllReferencedDocuments=Refs(refs)))
    assert _needed(e.value) == [os.path.realpath(a), os.path.realpath(b)]       # both, in one refusal


def test_no_scope_means_only_the_old_rules(tmp_path):
    assert writes.current_scope() is None
    writes.guard(str(tmp_path / "anywhere.ipt"))


def test_scope_comes_from_the_call_meta():
    assert writes.scope_from_meta({"progressToken": 1}) is None
    assert writes.scope_from_meta({"cad/write_scope": "junk"}) == {"dirs": [], "files": []}
    assert writes.scope_from_meta({"cad/write_scope": {"dirs": ["C:/j", 3], "files": None}}) == {"dirs": ["C:/j"],
                                                                                                "files": []}


def test_the_server_applies_the_scope_to_the_call(tmp_path):
    from inventor_forge.server import Server
    seen = {}
    srv = Server(visible=False)
    srv.forge.call = lambda name, args: seen.setdefault("scope", writes.current_scope()) or {}
    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
           "params": {"name": "status", "arguments": {}, "_meta": {"cad/write_scope": {"dirs": [str(tmp_path)]}}}}
    srv.handle(msg)
    assert seen["scope"] == {"dirs": [str(tmp_path)], "files": []} and writes.current_scope() is None
