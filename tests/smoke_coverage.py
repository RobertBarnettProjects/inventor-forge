"""Live run of the tools the other smoke scripts don't reach, each with a real check of the outcome.
API only: this never moves the mouse.  python -X utf8 tests/smoke_coverage.py
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

F = Forge()
FAIL = []
OUT = os.path.join(os.path.expanduser("~"), "Documents", "inventor-forge", "smoke")
os.makedirs(OUT, exist_ok=True)


def call(_tool, **args):
    res = F.safe_call(_tool, args)
    print(f"{_tool:24}", json.dumps(res, ensure_ascii=False)[:330])
    if not res["ok"]:
        FAIL.append((_tool, res.get("error"), res.get("trace", "")))
    return res


def expect(cond, msg):
    print(("   OK  " if cond else "   BAD ") + msg)
    if not cond:
        FAIL.append(("expect", msg, ""))


def near(a, b, rel=3e-3):
    return a is not None and abs(a - b) <= rel * max(abs(a), abs(b), 1e-9)


def clean():
    for d in F.safe_call("list_documents").get("documents", []):
        if d["name"].startswith(("Cov", "Drawing")):
            F.safe_call("close_document", {"name": d["name"]})
    F.safe_call("close_unused_documents")


clean()
print("\n== session / system")
call("status")
r = call("list_tools")
expect(r.get("count", 0) >= 100, "list_tools counts the registry")
r = call("list_materials", filter="Steel")
expect("Steel, Mild" in r.get("materials", []), "material library lists Steel, Mild")

print("\n== sketch + features")
call("create_part", name="CovBlock")
call("add_parameter", name="wall", expression="6 mm", comment="wall thickness")
call("create_sketch", plane="XY")
call("draw_rectangle", width=100, height=60, centered=False)
r = call("extrude", distance=20)
expect(near(r.get("volume_mm3"), 120000), "block volume")
p = call("get_parameters", user_only=True)
expect(any(x["name"] == "wall" and near(x["value"], 6) for x in p.get("user", [])), "user parameter reads 6 mm")
call("set_parameter", name="wall", expression="8 mm")
p = call("get_parameters", user_only=True)
expect(any(x["name"] == "wall" and near(x["value"], 8) for x in p.get("user", [])), "user parameter now 8 mm")

e = call("list_edges", type="line")
expect(e.get("total_edges") == 12, "12 edges on a block")
top = call("find_face", normal=[0, 0, 1])["face"]
ex = call("find_edge", x=50, y=0, z=20)["edge"]
ey = call("find_edge", x=0, y=30, z=20)["edge"]
r = call("hole_linear", face_index=top, edge_one=ex, distance_one=15, edge_two=ey, distance_two=20, diameter=8)
expect(near(-r.get("volume_change_mm3", 0), math.pi * 16 * 20), "hole_linear removes a Ø8 through hole")
cyl = [f for f in call("list_faces", type="cylinder")["faces"] if f.get("hole")]
if cyl:
    ax = cyl[0]["axis_point_mm"]
    expect(near(ax[0], 20, 0.02) and near(ax[1], 15, 0.02), f"hole sits 20/15 mm from the edges: {ax}")

call("create_sketch", plane="XY", offset=20)
call("draw_point", x=70, y=30)
r = call("hole", use_sketch_points=True, diameter=10, depth=5, face_index=0)
expect(near(-r.get("volume_change_mm3", 0), math.pi * 25 * 5, 0.2), f"sketch-point hole blind 5 mm: {r.get('volume_change_mm3')}")
r = call("select_sketch", index=1)
expect(r.get("sketch") == "Sketch1", "select_sketch switches sketch")

call("create_sketch", plane="XY", offset=20)
call("draw_arc", x=30, y=45, radius=6, start_angle=0, sweep_angle=180)
call("draw_line", x1=24, y1=45, x2=36, y2=45)
r = call("extrude", distance=3, operation="cut")
expect(near(-r.get("volume_change_mm3", 0), math.pi * 36 / 2 * 3), f"half-disc pocket from an arc + line: {r.get('volume_change_mm3')}")
feats = call("list_features")["features"]
last = feats[-1]["name"]
r = call("delete_feature", features=[last])
expect(r.get("volume_change_mm3", 0) > 0, "delete_feature gives the material back")

cyl = [f for f in call("list_faces", type="cylinder")["faces"] if abs(f["diameter_mm"] - 8) < 0.01]
if cyl:
    r = call("work_axis", face_index=cyl[0]["index"], name="HoleAxis")
    expect(r.get("work_axis") == "HoleAxis", "work_axis named")
call("set_view", view="top")
r = call("screenshot", path=os.path.join(OUT, "cov_top.png"))
expect(os.path.exists(r.get("path", "")), "screenshot written")
r = call("execute_python", code="print(cdef.Features.Count)\ncdef.SurfaceBodies.Count")
expect(r.get("result") == 1 and r.get("stdout", "").strip().isdigit(), "execute_python returns value and stdout")
call("set_material", name="Steel, Mild")
call("set_iproperties", properties={"part_number": "CB-1", "description": "Coverage block"})
path = os.path.join(OUT, "CovBlock.ipt")
if os.path.exists(path):
    os.remove(path)
call("save_document", path=path)

print("\n== exports")
for fmt, name in (("STEP", "cov.stp"), ("IGES", "cov.igs"), ("STL", "cov.stl"), ("SAT", "cov.sat"), ("OBJ", "cov.obj")):
    r = call("export_document", path=os.path.join(OUT, name), format=fmt)
    expect(r.get("bytes", 0) > 100, f"{fmt} export has content")
edges = call("list_edges")["edges"]
call("close_document")
r = call("open_document", path=path)
expect(r.get("opened", {}).get("type") == "part", "open_document reopens the part")
call("close_document")

print("\n== drawing detail")
d = call("create_drawing", sheet_size="A3")
call("add_base_view", model=path, x=130, y=170, scale=1, orientation="front", name="FRONT")
call("add_projected_view", parent="FRONT", x=130, y=240, name="TOP")
r = call("move_view", view="FRONT", x=140, y=160)
expect(near(r.get("view", {}).get("center_mm", [0])[0], 140, 0.01), "move_view")
r = call("set_view_scale", view="FRONT", scale=0.5)
expect(r.get("view", {}).get("scale") == "1:2", "set_view_scale")
call("set_view_scale", view="FRONT", scale=1)
horiz = [x for x in edges if x["type"] == "line" and near(x.get("length_mm"), 100) and abs(x["midpoint_mm"][2] - 20) < 1e-6]
vert = [x for x in edges if x["type"] == "line" and near(x.get("length_mm"), 60) and abs(x["midpoint_mm"][2] - 20) < 1e-6]
hole_edge = [x for x in edges if x["type"] == "circle" and near(x.get("diameter_mm"), 8) and abs(x["center_mm"][2] - 20) < 1e-6]
r = call("add_linear_dimension", view="FRONT", edge_one=horiz[0]["index"], direction="horizontal")
expect(near(r.get("dimension_mm"), 100), "single-edge linear dimension 100")
r = call("add_linear_dimension", view="FRONT", edge_one=horiz[0]["index"], edge_two=horiz[1]["index"], direction="vertical", x=240, y=160)
expect(near(r.get("dimension_mm"), 60), "two-edge dimension 60")
r = call("add_diameter_dimension", view="FRONT", edge=hole_edge[0]["index"])
expect(near(r.get("dimension_mm"), 8), "diameter dimension 8")
r = call("add_hole_note", view="FRONT", edge=hole_edge[0]["index"])
expect("8" in str(r.get("note", "")), f"hole note: {r.get('note')!r}")
r = call("add_general_notes", text="NOTES:\\n1. DEBURR ALL EDGES", x=30, y=50)
expect("DEBURR" in str(r.get("note", "")), "general note")
r = call("add_centermarks", view="FRONT")
expect(r.get("centermarks", 0) >= 1, "centre marks")
call("place_view_labels")
r = call("add_sheet", sheet_size="A4", orientation="portrait", name="Second")
expect(r.get("sheets") == 2, "second sheet added")
expect(r.get("sheet", {}).get("size_mm", [0, 0])[1] > r.get("sheet", {}).get("size_mm", [0, 0])[0], "A4 portrait")
r = call("activate_sheet", sheet="1")
expect(r.get("sheet", {}).get("views") == 2, "activate_sheet back to the first")
r = call("set_title_block_field", fields={"title": "COVERAGE", "drawing_number": "CB-1", "drawn_by": "RB"})
expect(len(r.get("set", {})) == 3, "title block fields set")
for fmt, name in (("DWG", "cov_sheet.dwg"), ("DXF", "cov_sheet.dxf")):
    r = call("export_document", path=os.path.join(OUT, name), format=fmt)
    expect(r.get("bytes", 0) > 1000, f"drawing {fmt} export has content")
r = call("render_sheet", path=os.path.join(OUT, "cov_sheet.png"))
call("close_document")

print("\n== assembly extras")
call("create_assembly", name="CovAsm")
call("place_component", path=path, grounded=False)
r = call("ground_component", occurrence="CovBlock:1")
expect(r.get("occurrence", {}).get("grounded") is True, "ground_component")
call("place_component", path=path, x=0, y=0, z=50, rotate_axis="Z", rotate_angle=90)
r = call("move_component", occurrence="CovBlock:2", x=10, y=20, z=60)
expect(near(r.get("occurrence", {}).get("position_mm", [0, 0, 0])[2], 60), "move_component")
r = call("check_interference")
expect(r.get("clear") is True, "no interference when apart")
r = call("move_component", occurrence="CovBlock:2", x=50, y=-10, z=0)
r = call("check_interference")
expect(r.get("count", 0) == 1 and r["interferences"][0]["volume_mm3"] > 1000, f"overlap detected with a volume: {r.get('interferences')}")
r = call("add_constraint", type="angle", occurrence_one="CovBlock:2", entity_one="XZ", occurrence_two="CovBlock:1", entity_two="XZ", angle=30)
expect("Health" in str(r.get("health")) or r.get("health"), f"angle constraint: {r.get('health')}")
ia = call("inspect_assembly")
expect(len(ia.get("constraints", [])) == 1, "constraint listed")
call("close_document")

print("\n== maintenance")
r = call("reload_api")
expect(r.get("tools", 0) >= 100 and not r.get("removed"), f"reload_api keeps all tools: {r.get('removed')}")
clean()

print("\nFAILURES:", len(FAIL))
for f in FAIL:
    print(" -", f[0], f[1])
    if f[2]:
        print(f[2][-700:])
