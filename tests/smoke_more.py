"""Live checks for sheet metal, assemblies and drawings (creates files under ~/Documents/inventor-forge/smoke)."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

F = Forge()
FAIL = []
OUT = os.path.join(os.path.expanduser("~"), "Documents", "inventor-forge", "smoke")
only = set(sys.argv[1:])
# start clean: files this script overwrites must not be held open from a previous run
for _d in list(F.safe_call("list_documents").get("documents", [])):
    if _d["name"].startswith(("Forge", "Drawing")):
        F.safe_call("close_document", {"name": _d["name"]})
F.safe_call("close_unused_documents")


def call(_tool, **args):
    res = F.safe_call(_tool, args)
    print(f"{_tool:22}", json.dumps(res, ensure_ascii=False)[:600])
    if not res["ok"]:
        FAIL.append((_tool, res.get("error"), res.get("trace", "")))
    return res


def section(name):
    return not only or name in only


if section("sheet"):
    print("\n== sheet metal")
    call("create_part", name="ForgeBracketSM", sheet_metal=True)
    call("set_sheet_metal_thickness", thickness=2, bend_radius=2)
    call("create_sketch", plane="XY")
    call("draw_rectangle", width=100, height=60)
    r = call("sheet_metal_face")
    e = call("find_edge", x=0, y=30, z=2)
    print("   flange edge", e.get("match"))
    call("flange", edges=[e["edge"]], height=25)
    call("create_sketch", face_index=call("find_face", normal=[0, 0, 1])["face"])
    call("draw_circle", diameter=12, x=0, y=0)
    call("sheet_metal_cut")
    fp = call("flat_pattern", dxf_path=os.path.join(OUT, "bracket_flat.dxf"))
    call("inspect")
    call("save_document", path=os.path.join(OUT, "ForgeBracketSM.ipt"))
    call("close_document")

if section("asm"):
    print("\n== parts for the assembly")
    call("create_part", name="ForgeBase")
    call("create_sketch", plane="XY")
    call("draw_rectangle", width=80, height=50)
    call("extrude", distance=12)
    call("hole", points=[[-25, 0], [25, 0]], diameter=10.5)
    call("set_material", name="Steel, Mild")
    call("set_iproperties", properties={"part_number": "FB-100", "description": "Base plate"})
    call("save_document", path=os.path.join(OUT, "ForgeBase.ipt"))
    call("close_document")
    call("create_part", name="ForgePin")
    call("create_sketch", plane="XY")
    call("draw_circle", diameter=10)
    call("extrude", distance=30)
    call("chamfer", distance=1, edges=[call("find_edge", z=30, type="circle")["edge"]])
    call("set_material", name="Steel")
    call("set_iproperties", properties={"part_number": "FP-010", "description": "Dowel pin 10 x 30"})
    call("save_document", path=os.path.join(OUT, "ForgePin.ipt"))
    call("close_document")
    print("\n== assembly")
    call("create_assembly", name="ForgeAsm")
    call("place_component", path=os.path.join(OUT, "ForgeBase.ipt"), grounded=True)
    call("place_component", path=os.path.join(OUT, "ForgePin.ipt"), x=-25, y=0, z=40)
    call("place_component", path=os.path.join(OUT, "ForgePin.ipt"), x=25, y=0, z=40)
    ia = call("inspect_assembly", faces_of="ForgeBase:1")
    holes = [f for f in ia["faces"] if f.get("hole")]
    pins = call("inspect_assembly", faces_of="ForgePin:1")
    pin_cyl = [f for f in pins["faces"] if f["type"] == "cylinder"][0]
    print("   holes", [(h["index"], h["axis_point_mm"]) for h in holes], "pin cyl", pin_cyl["index"])
    # pin axis -> hole axis (mate cylindrical faces = axes coincide), pin bottom flush with plate bottom
    hole_l = min(holes, key=lambda h: h["axis_point_mm"][0])
    hole_r = max(holes, key=lambda h: h["axis_point_mm"][0])
    call("add_constraint", type="mate", occurrence_one="ForgePin:1", entity_one=f"face:{pin_cyl['index']}",
         occurrence_two="ForgeBase:1", entity_two=f"face:{hole_l['index']}")
    call("add_constraint", type="mate", occurrence_one="ForgePin:2", entity_one=f"face:{pin_cyl['index']}",
         occurrence_two="ForgeBase:1", entity_two=f"face:{hole_r['index']}")
    call("add_constraint", type="flush", occurrence_one="ForgePin:1", entity_one="XY",
         occurrence_two="ForgeBase:1", entity_two="XY")
    call("add_constraint", type="flush", occurrence_one="ForgePin:2", entity_one="XY",
         occurrence_two="ForgeBase:1", entity_two="XY")
    ia = call("inspect_assembly")
    call("check_interference")
    call("bill_of_materials", csv_path=os.path.join(OUT, "bom.csv"))
    call("mass_properties")
    call("save_document", path=os.path.join(OUT, "ForgeAsm.iam"))

if section("draw"):
    print("\n== drawings")
    r = call("make_part_sheet", model=os.path.join(OUT, "ForgeBase.ipt"), title="BASE PLATE",
             drawing_number="FB-100", drawn_by="forge")
    call("list_views")
    call("render_sheet", path=os.path.join(OUT, "base_sheet.png"))
    call("export_pdf", path=os.path.join(OUT, "base_sheet.pdf"))
    call("save_document", path=os.path.join(OUT, "ForgeBase.dwg"))
    r = call("make_assembly_sheet", model=os.path.join(OUT, "ForgeAsm.iam"), title="PIN ASSEMBLY",
             drawing_number="FA-001")
    call("render_sheet", path=os.path.join(OUT, "asm_sheet.png"))
    call("export_pdf", path=os.path.join(OUT, "asm_sheet.pdf"))

print("\nFAILURES:", len(FAIL))
for f in FAIL:
    print(" -", f[0], f[1])
    if f[2]:
        print(f[2])
