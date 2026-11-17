"""Offline tests for print exports and multi-step building: mesh checks, 3MF writing, unit detection, selections,
profile parsing, batch references, per-body deltas and compact results. No Inventor needed.

    python -m pytest tests/test_print_and_build.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge import meshio  # noqa: E402
from inventor_forge.com import InventorError  # noqa: E402
from inventor_forge.registry import TOOLS, load_all  # noqa: E402

load_all()
B = sys.modules["inventor_forge.tools.build"]


def cube(x0=0.0, y0=0.0, z0=0.0, a=10.0):
    v = [(x0 + i * a, y0 + j * a, z0 + k * a) for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    idx = lambda i, j, k: v[i * 4 + j * 2 + k]  # noqa: E731
    quads = [((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)),     # bottom, facing -z
             ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)),     # top
             ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)),
             ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)),
             ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)),
             ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))]
    tris = []
    for q in quads:
        a_, b_, c_, d_ = (idx(*p) for p in q)
        tris += [(a_, b_, c_), (a_, c_, d_)]
    return tris


def test_mesh_stats_for_two_separate_cubes(tmp_path):
    tris = cube() + cube(20, 0, 0)
    st = meshio.stats(tris)
    assert st["triangles"] == 24 and st["shells"] == 2 and st["watertight"]
    assert st["volume_mm3"] == pytest.approx(2000) and st["bed_contact_mm2"] == pytest.approx(200)
    assert st["size_mm"] == [30, 10, 10]
    p = tmp_path / "a.stl"
    meshio.write_stl(str(p), tris)
    assert meshio.stats(meshio.read_stl(str(p)))["shells"] == 2


def test_open_mesh_is_reported():
    st = meshio.stats(cube()[:-1])
    assert st["open_edges"] > 0 and not st["watertight"]


def test_3mf_round_trip_in_millimetres(tmp_path):
    p = tmp_path / "a.3mf"
    info = meshio.write_3mf(str(p), cube(), name="box & lid")
    assert info["vertices"] == 8 and info["triangles"] == 12
    tris, unit = meshio.read_3mf(str(p))
    assert unit == "millimeter" and meshio.stats(tris)["size_mm"] == [10, 10, 10]


def test_mesh_units_are_recognised():
    assert meshio.scale_hint([1, 2, 3], [10, 20, 30]) == 10.0
    assert meshio.scale_hint([10, 20, 30], [10, 20, 30]) == 1.0
    assert meshio.scale_hint([10, 20, 30], [13, 20, 30]) is None


def test_mesh_check_flags_merged_bodies():
    P = sys.modules["inventor_forge.tools.printing"]
    tris = cube()
    st, problems, k = P.check_mesh(tris, [10, 10, 10], 2)
    assert k == 1.0 and any("shells" in p for p in problems)
    tris = meshio.scaled(cube(), 0.1)              # written in cm
    st, problems, k = P.check_mesh(tris, [10, 10, 10], 1)
    assert k == 10.0 and st["size_mm"] == [10, 10, 10] and not problems


def test_edge_filters():
    row = {"type": "line", "length_mm": 20.0, "midpoint_mm": [10, 0, 5]}
    assert B.edge_matches(row, [[0, 0, 5], [20, 0, 5]], plane={"axis": "z", "at": 5})
    assert not B.edge_matches(row, [[0, 0, 5], [20, 0, 6]], plane={"axis": "z", "at": 5})
    assert B.edge_matches(row, [], box=[0, -1, 0, 20, 1, 10]) and not B.edge_matches(row, [], box=[11, -1, 0, 20, 1, 10])
    assert not B.edge_matches(row, [], type="circle") and not B.edge_matches(row, [], min_length=25)


def test_profile_loops():
    steps = B.parse_loop([["0", "0"], ["L", "0"], {"arc": ["L", "2*R"], "center": ["L", "R"]}, ["0", "2*R"]])
    assert [x["kind"] for x in steps] == ["start", "line", "arc", "line"]
    assert B.parse_loop({"circle": ["0", "0"], "radius": "R"})[0]["kind"] == "circle"
    with pytest.raises(InventorError, match="centre"):
        B.parse_loop([["0", "0"], {"arc": ["1", "1"]}, ["0", "1"]])
    assert B.arc_radius_mismatch([10, 0], [0, 10], [0, 0]) == 0
    assert B.arc_radius_mismatch([10, 0], [0, 12], [0, 0]) == pytest.approx(2)


def test_batch_references_and_limits():
    outs = {"top": {"edges": [3, 7], "feature": "Extrusion1"}}
    assert B.resolve_refs({"edges": "$top.edges", "f": ["$top.feature"]}, outs) == {"edges": [3, 7],
                                                                                    "f": ["Extrusion1"]}
    assert B.resolve_refs("$top.edges.1", outs) == 7
    with pytest.raises(InventorError, match="no earlier step"):
        B.resolve_refs("$nope.x", outs)
    with pytest.raises(InventorError, match="can't run inside a batch"):
        TOOLS["batch"].fn(None, steps=[{"tool": "close_document"}])


def test_per_body_volume_changes():
    from inventor_forge.session import body_changes
    assert body_changes({"Rotor": 100.0, "Stator": 50.0}, {"Rotor": 88.0, "Stator": 50.0, "Cutter": 5.0}) == \
        {"Rotor": -12.0, "Cutter": "new (5 mm³)"}


def test_compact_results():
    from inventor_forge.engine import compact
    res = {"images": [{"view": "iso", "path": r"C:\w\renders\a-iso.png", "note": "orthographic"},
                      {"view": "top", "path": r"C:\w\renders\a-top.png", "note": "orthographic"}]}
    out = compact(res)
    assert out["folder"] == r"C:\w\renders" and out["images"][1]["path"] == "a-top.png"
    assert "note" in out["images"][0] and "note" not in out["images"][1]


def test_part_two_tools_registered():
    for n in ("export_print_package", "export_capabilities", "list_bodies", "body_gap", "pose_bodies",
              "select_edges", "select_faces", "parametric_profile", "batch", "set_output", "guide"):
        assert n in TOOLS, n
    for t, arg in (("extrude", "body"), ("hole", "body"), ("fillet", "body"), ("chamfer", "body"),
                   ("find_edge", "strict"), ("find_face", "body"), ("measure", "body_two"),
                   ("screenshot", "field_mm"), ("screenshot", "target")):
        assert arg in TOOLS[t].schema["properties"], (t, arg)
