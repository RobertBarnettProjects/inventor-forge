"""The cad/* tool profile published to MCP clients, and progress notifications during a call (no Inventor needed)."""
import threading
import time

from inventor_forge import profile, server
from inventor_forge.registry import load_all


def _meta():
    tools = load_all()
    return {name: profile.tool_meta(t) for name, t in tools.items()}


def test_every_tool_has_a_budget_and_progress():
    for name, meta in _meta().items():
        assert meta["cad/budget"]["floor_s"] >= 60, name
        assert meta["cad/progress"] is True


def test_profile_flags():
    m = _meta()
    assert m["extrude"].get("cad/geometry") is True
    assert "cad/geometry" not in m["list_faces"]
    assert m["analyze_stress"]["cad/takes_input"] is True
    assert m["study_report"]["cad/takes_input"] == {"if_args": {"only_this_study": True}}
    assert m["execute_python"]["cad/runs_code"] is True
    assert m["export_pdf"]["cad/files"]["writes"] == ["path"]


def test_every_listed_flag_names_a_real_tool():
    tools = load_all()
    for group in (profile.GEOMETRY, set(profile.TAKES_INPUT), profile.RUNS_CODE):
        assert not (group - set(tools)), group - set(tools)


def test_budget_rule_matches_the_engine():
    from inventor_forge.engine import DEFAULT_WAIT, call_budget
    tools = load_all()
    for name in ("run_study_cases", "solve_study", "extrude"):
        t = tools[name]
        meta = profile.tool_meta(t)["cad/budget"]
        for args in ({}, {"timeout": 100}, {"timeout": 100, "cases": [{}, {}, {}]}):
            assert profile.budget_for({**meta, "floor_s": DEFAULT_WAIT}, args) == call_budget(t.fn, args)


def test_three_cases_wait_three_times_as_long():
    meta = profile.tool_meta(load_all()["run_study_cases"])["cad/budget"]
    one = profile.budget_for(meta, {"timeout": 1000, "cases": [{}]})
    three = profile.budget_for(meta, {"timeout": 1000, "cases": [{}, {}, {}]})
    assert three - one == 2 * (1000 + meta["per_item_s"])


def test_heartbeat_sends_progress_until_stopped(monkeypatch):
    monkeypatch.setattr(server, "PROGRESS_EVERY", 0.05)
    sent = []
    s = server.Server.__new__(server.Server)          # no Forge: only the heartbeat is exercised

    class _Sess:
        progress = "meshing"

    class _Forge:
        session = _Sess()
    s.forge = _Forge()
    s.emit = sent.append
    stop = threading.Event()
    th = threading.Thread(target=s._heartbeat, args=("solve_study", 7, stop))
    th.start()
    time.sleep(0.3)
    stop.set()
    th.join(2)
    assert len(sent) >= 2
    p = sent[0]["params"]
    assert sent[0]["method"] == "notifications/progress" and p["progressToken"] == 7
    assert "solve_study: meshing" in p["message"]
    n = len(sent)
    time.sleep(0.15)
    assert len(sent) == n                              # nothing after the call ended


def test_initialize_advertises_the_profile():
    s = server.Server.__new__(server.Server)
    r = server.Server.handle(s, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    prof = r["result"]["capabilities"]["experimental"]["cad/profile"]
    assert prof["family"] == "inventor" and prof["version"] == profile.PROFILE_VERSION
