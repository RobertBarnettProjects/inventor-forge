"""Tests that need neither Inventor nor a display: tool registry/schemas, the MCP protocol layer,
and the parser for Inventor stress-analysis reports (on a real, anonymised report).

    python -m pytest tests/test_offline.py
"""
import json
import math
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.tools.fea import parse_report  # noqa: E402
from inventor_forge.registry import load_all  # noqa: E402

CORE_TOOLS = """activate_document activate_sheet add_base_view add_constraint add_general_notes add_hole_note
add_linear_dimension add_parameter add_parts_list add_projected_view add_sheet auto_balloon auto_dimension_view
chamfer check_drawing check_interference circular_pattern close_document connect create_assembly create_drawing
create_part create_sketch delete_feature draw_circle draw_closed_profile draw_line draw_polygon draw_rectangle
edit_dimension execute_python export_document export_pdf extrude fillet find_edge find_face flange get_parameters
hole hole_linear inspect inspect_assembly list_dimensions list_edges list_faces list_features list_views
make_assembly_sheet make_part_sheet open_document place_component place_view_labels reload_api render_sheet
revolve save_document set_iproperties set_material set_parameter set_sheet_metal_thickness set_title_block_field
set_view sheet_metal_cut sheet_metal_face status suppress_feature transaction""".split()


def test_every_tool_has_a_description_and_valid_schema():
    tools = load_all()
    assert len(tools) >= 95
    for t in tools.values():
        assert t.description and len(t.description) > 20, t.name
        assert t.schema["type"] == "object"
        for name, spec in t.schema["properties"].items():
            assert "type" in spec or spec == {} or "description" in spec, (t.name, name)
        json.dumps(t.schema)


def test_core_tool_set_is_present():
    tools = load_all()
    missing = [n for n in CORE_TOOLS if n not in tools]
    assert not missing, missing


def test_mcp_protocol_initialize_and_list():
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "nope"}]
    p = subprocess.run([sys.executable, "-X", "utf8", "-m", "inventor_forge.server"],
                       input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True,
                       cwd=os.path.join(os.path.dirname(__file__), ".."), timeout=60, encoding="utf-8")
    replies = [json.loads(line) for line in p.stdout.splitlines() if line.strip()]
    assert [r["id"] for r in replies] == [1, 2, 3]
    assert replies[0]["result"]["serverInfo"]["name"] == "inventor-forge"
    assert len(replies[1]["result"]["tools"]) >= 95
    assert replies[2]["error"]["code"] == -32601


FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "inventor_report_3_studies.html")


def test_report_parser_reads_the_requested_study():
    """Inventor's report lists every study in the document; the parser must read the right one."""
    last = parse_report(FIXTURE)                       # default: the newest study (modal)
    assert last["study"] == "Modal Analysis:1"
    assert last["frequencies_Hz"][:3] == [383.31, 755.14, 2355.99]   # beam theory: 380 / 760 / 2382 Hz
    s1 = parse_report(FIXTURE, "Static Analysis:1")
    assert s1["mesh_avg_size_fraction"] == 0.1
    assert s1["summary"]["Von Mises Stress"]["max"] == pytest.approx(83.93, abs=0.01)
    assert s1["summary"]["Displacement"]["max"] == pytest.approx(0.6089, abs=1e-3)   # PL^3/3EI = 0.6136 mm
    assert s1["reactions"][0]["force_N"] == pytest.approx(200)
    assert s1["reactions"][0]["moment_Nm"] == pytest.approx(30.0, abs=0.01)            # 200 N x 150 mm
    assert s1["loads"][0]["vector_z"].startswith("-200")
    s2 = parse_report(FIXTURE, "Static Analysis:2")
    assert s2["mesh_avg_size_fraction"] == 0.04
    assert s2["summary"]["Von Mises Stress"]["max"] == pytest.approx(88.54, abs=0.01)  # finer mesh -> nearer 90 MPa
    assert s2["material"]["yield_MPa"].startswith("207")


def test_analysis_needs_the_user_go_ahead_first():
    """Without user_notified=true the analysis tools touch nothing and return the mouse/keyboard notice."""
    from inventor_forge.tools.fea import analyze_modes, analyze_stress
    r = analyze_stress(None, fixed_faces=[1], loads=[{"face": 2, "force": [0, 0, -1]}])
    assert r["status"] == "needs_user_go_ahead" and "MOUSE AND KEYBOARD" in r["notice"]
    assert analyze_modes(None, fixed_faces=[1])["status"] == "needs_user_go_ahead"


def test_report_parser_finds_renamed_studies(tmp_path):
    """Studies are usually given their own names, so the section heading can be anything."""
    with open(FIXTURE, encoding="utf-8", errors="replace") as f:
        text = f.read().replace(">Static Analysis:2<", ">Pull 15deg - 30mm plate<")
    p = tmp_path / "named.html"
    p.write_text(text, encoding="utf-8")
    assert parse_report(str(p), "Pull 15deg - 30mm plate")["summary"]["Von Mises Stress"]["max"] == pytest.approx(88.54, abs=0.01)
    assert parse_report(str(p), "Static Analysis:1")["mesh_avg_size_fraction"] == 0.1
    with pytest.raises(Exception, match="not in this report"):
        parse_report(str(p), "No such study")


def test_value_box_comparison():
    from inventor_forge.uidrive import same_value
    assert same_value("2.000 MPa", "2 MPa") and same_value("0.070", "0.07") and same_value("-30.000 N", "-30")
    assert not same_value("", "0.07") and not same_value("20.000 N", "2")


def test_busy_inventor_retries_reads_but_not_edits():
    import pywintypes
    from inventor_forge.engine import Forge
    from inventor_forge.registry import TOOLS, tool

    calls = {"read": 0, "edit": 0}
    busy = pywintypes.com_error(-2147418111, "Call was rejected by callee.", None, None)

    @tool("system", name="_read_probe", mutates=False)
    def _read(s) -> dict:
        """Test double that is refused twice and then succeeds."""
        calls["read"] += 1
        if calls["read"] < 3:
            raise busy
        return {"value": 1}

    @tool("system", name="_edit_probe")
    def _edit(s) -> dict:
        """Test double for an edit that Inventor refuses."""
        calls["edit"] += 1
        raise busy

    forge = Forge()
    forge.session.solver_busy = lambda: []
    try:
        assert forge.safe_call("_read_probe", {}) == {"ok": True, "value": 1}
        r = forge.safe_call("_edit_probe", {})
        assert not r["ok"] and "busy" in r["error"] and calls["edit"] == 1
    finally:
        TOOLS.pop("_read_probe"), TOOLS.pop("_edit_probe")


def test_tools_refuse_while_a_solve_is_running():
    from inventor_forge.engine import Forge
    forge = Forge()
    forge.session.solver_busy = lambda: ["Simulate"]
    r = forge.safe_call("status", {})
    assert not r["ok"] and "solve" in r["error"]
    forge.session.solver_busy = lambda: []


def test_private_session_never_falls_back_to_the_users_inventor():
    from inventor_forge.com import InventorError
    from inventor_forge.session import Session

    class Dead:
        @property
        def Caption(self):
            raise OSError("gone")

    s = Session()
    s._app, s.private, s.pid = Dead(), True, 123
    s._connect = lambda: pytest.fail("attached to another Inventor")
    with pytest.raises(InventorError, match="private Inventor"):
        _ = s.app



def test_batch_restarts_its_own_inventor_and_carries_on(tmp_path, monkeypatch):
    """When the private Inventor running a batch dies, a new one is started, the file reopened, and the batch goes on."""
    from inventor_forge.tools import studies

    class Docs:
        def Open(self, path, visible):
            return "doc"

    class App:
        Documents = Docs()

    class FakeSession:
        private, pid, workdir = True, 111, str(tmp_path)
        _app = None
        started = 0

        def doc(self):
            class D:
                FullFileName = str(tmp_path / "part.ipt")
                DisplayName = "part.ipt"
            return D()

        def start_private(self):
            FakeSession.started += 1
            self.private, self.pid = True, 222

        @property
        def app(self):
            return App()

        def set_current(self, d):
            pass

    s = FakeSession()
    alive = {111}
    calls = []

    def run_case(sess, pid, template, case, want, timeout, data, path):
        calls.append((case["name"], pid))
        if len(calls) == 1:
            alive.discard(111)
            raise RuntimeError("RPC server unavailable")
        data["cases"][case["name"]] = {"status": "done", "results": {}}

    monkeypatch.setattr(studies, "_pid", lambda sess: sess.pid)
    monkeypatch.setattr(studies, "_study_nodes", lambda sess: {"T": object()})
    monkeypatch.setattr(studies, "_run_case", run_case)
    monkeypatch.setattr(studies, "_enter_analysis", lambda sess: None)
    monkeypatch.setattr(studies.U, "pids_named", lambda exe: sorted(alive | {222}))
    r = studies.run_study_cases(s, template="T", cases=[{"name": "A"}, {"name": "B"}], results_path=str(tmp_path / "r.json"))
    assert r["inventor_restarts"] == 1 and r["ran"] == 2 and FakeSession.started == 1
    assert calls == [("A", 111), ("A", 222), ("B", 222)]
