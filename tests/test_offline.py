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
