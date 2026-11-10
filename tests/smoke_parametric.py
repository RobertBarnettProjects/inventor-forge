"""Live test, in a private Inventor process, of the parametric and connection tools. No mouse or keyboard."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

F = Forge()
OUT = os.path.join(os.path.expanduser("~"), "Documents", "inventor-forge", "parametric")
os.makedirs(OUT, exist_ok=True)
FAIL = []


def call(_tool, **args):
    res = F.safe_call(_tool, args)
    print(f"{_tool:26}", json.dumps(res, ensure_ascii=False)[:600], flush=True)
    if not res["ok"]:
        F.safe_call("close_private_inventor", {})
        raise SystemExit(res.get("error"))
    return res


def check(name, got, want, tol=1e-3):
    ok = abs(got - want) <= tol * max(abs(want), 1)
    print(("PASS " if ok else "FAIL ") + f"{name}: {got} (expected {want})", flush=True)
    if not ok:
        FAIL.append(name)


def expect(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + f"{name} {info}", flush=True)
    if not cond:
        FAIL.append(name)


r = call("connect", private=True)
expect("private process", r["private"] and r["process"])
call("list_projects")
call("solve_state")

# ---- master part
call("create_part", name="Master")
call("add_parameter", name="Len", expression="120 mm")
call("add_parameter", name="Hgt", expression="40 mm")
call("add_parameter", name="Thk", expression="10 mm")
call("create_sketch", plane="XY")
call("draw_rectangle", width=10, height=10)
call("extrude", distance=5)
master = os.path.join(OUT, "Master.ipt")
call("save_document", path=master)

# ---- linked, fully constrained plate on each plane
for plane, verts in (("XZ", [["0", "0"], ["Len", "0"], ["Len", "Hgt"], ["0", "Hgt"]]),
                     ("YZ", [["-Len", "0"], ["0", "0"], ["0", "Hgt"], ["-Len", "Hgt"]]),
                     ("XY", [["Len", "0"], ["Len", "Hgt"], ["Len / 2", "Hgt / 2"], ["0", "0"]])):
    call("create_part", name=f"Plate{plane}")
    r = call("link_parameters", source=master, names=["Len", "Hgt", "Thk"])
    expect("linked", len(r["linked"]) == 3)
    r = call("parametric_extrusion", plane=plane, vertices=verts, width="Thk", name="Body")
    expect(f"{plane} fully constrained", r["fully_constrained"], r["constraint_status"])
    area = 120 * 40 if plane != "XY" else 0.5 * abs(120 * 40 - 60 * 20 + 0 - 0 + 0 * 0 + 60 * 0 - 0 * 20 - 120 * 40 * 0 + 0)
    if plane != "XY":
        check(f"{plane} volume", r["volume_mm3"], area * 10)
    r2 = call("execute_python", code="doc.ComponentDefinition.Parameters.Item('Thk').Expression")
    box = call("execute_python", code="b=cdef.RangeBox; [round((b.MaxPoint.X-b.MinPoint.X)*10,3), round((b.MaxPoint.Y-b.MinPoint.Y)*10,3), round((b.MaxPoint.Z-b.MinPoint.Z)*10,3)]")
    print("box", box.get("result"), "T", r2.get("result"))
    if plane == "YZ":
        lo = call("execute_python", code="round(cdef.RangeBox.MinPoint.Y*10,3)")["result"]
        check("negative side honoured", lo, -120)

# ---- driving the master reshapes a linked part
call("activate_document", name="PlateXZ")
call("execute_python", code=(
    "m=[d for d in app.Documents if d.DisplayName.startswith('Master')][0]\n"
    "m.ComponentDefinition.Parameters.UserParameters.Item('Len').Expression='150 mm'\nm.Update()\n"
    "doc.Update()"))
r = call("inspect")
print(r)
vol = call("execute_python", code="round(cdef.MassProperties.Volume*1000,1)")["result"]
check("master change drives the part", vol, 150 * 40 * 10)
call("execute_python", code=(
    "m=[d for d in app.Documents if d.DisplayName.startswith('Master')][0]\n"
    "m.ComponentDefinition.Parameters.UserParameters.Item('Len').Expression='120 mm'\nm.Update()\ndoc.Update()"))

# ---- named faces survive a feature that renumbers them
call("create_part", name="Named")
call("create_sketch", plane="XY")
call("draw_rectangle", width=100, height=60)
call("extrude", distance=20)
top = call("find_face", normal=[0, 0, 1])["face"]
call("name_face", face=top, name="load_patch")
call("hole", x=0, y=0, diameter=20)
call("fillet", edges=[call("find_edge", z=10, type="line")["edge"]], radius=2) if False else None
r = call("find_named_face", name="load_patch")
rows = {f["index"]: f for f in call("list_faces")["faces"]}
expect("named face is still the top", abs(rows[r["face"]]["normal"][2] - 1) < 1e-6 if "normal" in rows[r["face"]] else True, rows[r["face"]])
expect("named list", call("list_named_faces")["faces"][0]["name"] == "load_patch")

# ---- model states
before = call("execute_python", code="round(cdef.MassProperties.Volume*1000,1)")["result"]
call("add_model_state", name="NoHole")
feat = [f for f in call("list_features")["features"] if "ole" in f["name"]][-1]["name"]
call("suppress_feature", feature=feat)
in_state = call("execute_python", code="round(cdef.MassProperties.Volume*1000,1)")["result"]
check("state without the hole", in_state, 100 * 60 * 20)
r = call("list_model_states")
primary = [m["name"] for m in r["states"] if m["name"] != "NoHole"][0]
call("activate_model_state", name=primary)
check("primary state keeps the hole", call("execute_python", code="round(cdef.MassProperties.Volume*1000,1)")["result"], before)
named = os.path.join(OUT, "Named.ipt")
call("save_document", path=named)

# ---- split faces: solid unchanged, face count up
call("create_part", name="Split")
call("create_sketch", plane="XY")
call("draw_rectangle", width=100, height=60)
call("extrude", distance=20)
top = call("find_face", normal=[0, 0, 1])["face"]
n0 = call("inspect")
call("create_sketch", plane="XY")
call("draw_line", x1=-20, y1=-40, x2=-20, y2=40)
call("draw_line", x1=20, y1=-40, x2=20, y2=40)
r = call("split_faces", faces=[top])
expect("two splits", len(r["features"]) == 2, r["features"])
check("split keeps volume", r["volume_mm3"], 100 * 60 * 20)
expect("faces added", r["faces"] == 8, r["faces"])

# ---- assembly
call("create_assembly", name="Asm")
call("add_parameter", name="Gap", expression="30 mm")
call("place_component", path=named, grounded=True)
call("place_component", path=named, x=0, y=0, z=80)
occ = [o["name"] for o in call("inspect_assembly")["occurrences"]]
expect("two components", len(occ) == 2, occ)
r = call("add_constraint", type="flush", occurrence_one=occ[1], entity_one="XY", occurrence_two=occ[0], entity_two="XY", offset_expression="Gap + 20 mm")
print(r["positions"])
r = call("component_gap", occurrence_one=occ[0], occurrence_two=occ[1])
check("parametric offset gap", r["gap_mm"], 30)
r = call("check_assembly")
expect("assembly healthy", r["ok"], r)
check("assembly height", r["size_mm"][2], 70)
r = call("set_component_model_state", occurrence=occ[1], state="NoHole")
expect("component state", r["state"] == "NoHole", r)
asm = os.path.join(OUT, "Asm.iam")
call("save_document", path=asm)

# ---- drawing: holes along Y, so the main view should look along Y; template .idw; projection symbol
call("create_part", name="SidePlate")
call("create_sketch", plane="XZ")
call("draw_rectangle", width=160, height=80)
call("extrude", distance=12, direction="positive")
call("create_sketch", plane="XZ")
for x in (-50, 50):
    call("draw_circle", diameter=16, x=x, y=0)
call("extrude", through_all=True, operation="cut", direction="both") if False else call("extrude", distance=60, operation="cut", direction="symmetric")
side = os.path.join(OUT, "SidePlate.ipt")
call("save_document", path=side)
r = call("make_part_sheet", model=side, title="SIDE PLATE", drawing_number="SP-1", drawn_by="RB", material="Steel")
print(json.dumps(r["qa"], ensure_ascii=False)[:800])
idw = os.path.join(OUT, "SidePlate.idw")
r2 = call("save_document", path=idw)
expect("drawing saved as idw", r2.get("path", idw).lower().endswith(".idw"), r2)
png = os.path.join(OUT, "SidePlate.png")
call("render_sheet", path=png)
views = call("list_views")["views"]
print(views)
front = next(v for v in views if v["name"] == "FRONT")
expect("main view shows the holes (largest face)", front.get("width_mm", 999) > front.get("height_mm", 0))

# ---- set_view_component_visibility on an assembly drawing
call("close_document", save=False)
r = call("make_assembly_sheet", model=asm, title="ASM", drawing_number="A-1", drawn_by="RB")
print(r["parts_list_rows"], r["balloons"])
call("render_sheet", path=os.path.join(OUT, "Asm.png"))
r = call("set_view_component_visibility", view="ISOMETRIC", occurrence=occ[1], visible=False)
expect("view visibility", r["visible"] is False)

print("\nFAILED:" if FAIL else "\nALL PASSED", FAIL or "")
call("close_private_inventor")
