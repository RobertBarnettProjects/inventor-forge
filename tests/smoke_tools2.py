"""Live checks of the second batch of tools (API only, never moves the mouse)."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

F = Forge()
FAIL = []
OUT = os.path.join(os.path.expanduser("~"), "Documents", "inventor-forge", "smoke")


def call(_tool, **args):
    res = F.safe_call(_tool, args)
    print(f"{_tool:24}", json.dumps(res, ensure_ascii=False)[:300], flush=True)
    if not res["ok"]:
        FAIL.append((_tool, res.get("error"), res.get("trace", "")))
    return res


def expect(cond, msg):
    print(("   OK  " if cond else "   BAD ") + msg, flush=True)
    if not cond:
        FAIL.append(("expect", msg, ""))


def near(a, b, rel=3e-3):
    return a is not None and abs(a - b) <= rel * max(abs(a), abs(b), 1e-9)


def clean():
    for d in F.safe_call("list_documents").get("documents", []):
        if d["name"].startswith(("Tb", "Drawing", "HexBolt", "SocketScrew", "HexNut", "Washer", "Dowel", "ForgeFlange")):
            F.safe_call("close_document", {"name": d["name"]})
    F.safe_call("close_unused_documents")


section = sys.argv[1:] or ["sketch", "features", "standard", "drawing", "extras"]
clean()

if "sketch" in section:
    print("\n== sketch tools")
    call("create_part", name="TbSketch")
    call("create_sketch", plane="XY")
    call("draw_closed_profile", points=[[0, 0], [40, 0], [40, 30], [0, 30]])
    rows = call("list_sketch_curves")["curves"]
    expect(len(rows) == 4 and rows[0]["type"] == "line", "four lines listed")
    r = call("add_sketch_constraint", type="horizontal", curve_one=1)
    expect(r.get("constraints", 0) >= 1, "horizontal constraint")
    call("add_sketch_constraint", type="vertical", curve_one=2)
    call("add_sketch_constraint", type="parallel", curve_one=1, curve_two=3)
    call("add_sketch_constraint", type="perpendicular", curve_one=3, curve_two=4)
    r = call("add_sketch_dimension", curve=1, value="50 mm", kind="horizontal", x=20, y=-8)
    expect(near(r.get("value"), 50), "dimension drives the line to 50 mm")
    r = call("add_sketch_dimension", curve=2, value="30 mm", kind="vertical", x=60, y=15)
    r = call("extrude", distance=10)
    expect(near(r.get("volume_mm3"), 50 * 30 * 10), f"sketch solved to 50 x 30: {r.get('volume_mm3')}")
    top = call("find_face", normal=[0, 0, 1])["face"]
    call("create_sketch", face_index=top)
    e = call("find_edge", z=10, x=25, y=0)["edge"]
    call("project_edges", edges=[e])
    call("create_sketch", plane="XY", offset=10)
    call("draw_circle", diameter=10, x=25, y=15)
    r = call("offset_sketch", curves=[1], distance=2)
    expect(r.get("created", 0) >= 1, "offset created a curve")
    r = call("extrude", distance=2, operation="cut")
    expect(near(-r.get("volume_change_mm3", 0), math.pi / 4 * (14 ** 2 - 10 ** 2) * 2) or near(-r.get("volume_change_mm3", 0), math.pi / 4 * (10 ** 2 - 6 ** 2) * 2), f"annular pocket between the offset circles: {r.get('volume_change_mm3')}")
    call("close_document")

if "features" in section:
    print("\n== feature tools")
    call("create_part", name="TbFeat")
    call("create_sketch", plane="XY")
    call("draw_rectangle", width=60, height=40)
    call("extrude", distance=20)
    r = call("split_part", plane="XY", remove="negative") if False else None
    call("work_plane", base="XY", offset=10, name="Mid")
    r = call("split_part", plane="Mid", keep_both=True)
    expect(r.get("bodies") == 2, "split into two bodies")
    r = call("combine_bodies", operation="join")
    expect(near(call("inspect")["volume_mm3"], 60 * 40 * 20), "combine restores the block")
    r = call("split_part", plane="Mid", remove="positive")
    v1 = call("inspect")["volume_mm3"]
    expect(near(v1, 60 * 40 * 10), f"trim keeps half: {v1}")
    side = call("find_face", normal=[1, 0, 0])["face"]
    r = call("face_draft", faces=[side], angle=5, pull_plane="XY")
    expect(abs(r.get("volume_change_mm3", 0)) > 1, f"draft changes the volume: {r.get('volume_change_mm3')}")
    top = call("find_face", normal=[0, 0, 1])["face"]
    r = call("thicken_face", faces=[top], distance=3)
    expect(r.get("volume_change_mm3", 0) > 1000, f"thicken adds material: {r.get('volume_change_mm3')}")
    top = call("find_face", normal=[0, 0, 1])["face"]
    r = call("emboss_text", text="FORGE", x=0, y=0, depth=0.5, height=6, face_index=top)
    expect(r.get("volume_change_mm3", 1) < 0, f"engraved text removes material: {r.get('volume_change_mm3')}")
    call("close_document")
    call("create_part", name="TbCoil")
    call("create_sketch", plane="XZ")
    call("draw_circle", diameter=2, x=10, y=0)
    r = call("coil", pitch=4, revolutions=5, axis="Z")
    lh = math.sqrt((2 * math.pi * 10) ** 2 + 16) * 5
    expect(near(r.get("volume_mm3"), math.pi * lh, 0.03), f"coil volume {r.get('volume_mm3')} vs ~{math.pi * lh:.0f}")
    call("close_document")

if "standard" in section:
    print("\n== standard parts")
    for kind, size, length in (("hex_bolt", "M10", 40), ("socket_screw", "M8", 30), ("hex_nut", "M10", 0),
                               ("washer", "M10", 0), ("dowel", "8", 24)):
        r = call("create_standard_part", kind=kind, size=size, length=length,
                 save_path=os.path.join(OUT, f"std_{kind}_{size}.ipt"))
        expect(not r.get("warning") and r.get("volume_mm3", 0) > 0, f"{kind} {size}: V {r.get('volume_mm3')} vs {r.get('expected_volume_mm3')}")
        call("screenshot", path=os.path.join(OUT, f"std_{kind}.png"), view="iso")
        call("close_document")

if "drawing" in section:
    print("\n== round part drawing + annotations")
    call("create_part", name="ForgeFlange")
    call("create_sketch", plane="XZ")
    call("draw_closed_profile", points=[[20, 0], [75, 0], [75, 16], [35, 16], [35, 40], [20, 40]])
    call("revolve", axis="Z")
    h = call("hole", x=55, y=0, diameter=14, cbore_diameter=22, cbore_depth=4)
    call("circular_pattern", features=[h["feature"]], count=6, axis="Z")
    call("set_material", name="Steel, Mild")
    call("set_iproperties", properties={"part_number": "FF-080", "description": "Flange"})
    path = os.path.join(OUT, "ForgeFlange.ipt")
    call("save_document", path=path)
    r = call("make_part_sheet", model=path, views="front,top,iso", title="FLANGE", drawing_number="FF-080", drawn_by="RB")
    print("   callouts", r.get("callouts"), "overall", r.get("overall"), "qa", r.get("qa", {}).get("issues"))
    expect((r.get("callouts") or {}).get("hole_groups", 0) >= 1, "hole group callout")
    dims = call("list_drawing_dimensions")["dimensions"]
    vals = [d["value_mm"] for d in dims]
    expect(any(near(v, 150) for v in vals), f"outer Ø150 dimensioned: {vals}")
    expect(any(near(v, 40) for v in vals), "bore / height 40 dimensioned")
    i150 = next(d["index"] for d in dims if near(d["value_mm"], 150))
    r = call("set_dimension_tolerance", index=i150, symmetric=0.2)
    expect("Symmetric" in r.get("tolerance", ""), f"symmetric tolerance: {r}")
    r = call("add_revision_table"); print("   rev", r.get("box_mm"))
    expect(r.get("rows", 0) >= 1, "revision table")
    r = call("add_hole_table", view="FRONT", x=250, y=120) if False else None
    q = call("check_drawing")
    call("render_sheet", path=os.path.join(OUT, "flange_callouts.png"))
    call("close_document")

if "extras" in section:
    print("\n== remaining annotation and assembly tools")
    base = os.path.join(OUT, "CovBlock.ipt")
    edges = None
    call("open_document", path=base)
    edges = call("list_edges")["edges"]
    call("close_document")
    horiz = [x for x in edges if x["type"] == "line" and near(x.get("length_mm"), 100) and abs(x["midpoint_mm"][2] - 20) < 1e-6]
    call("create_drawing", sheet_size="A3")
    call("add_base_view", model=base, x=140, y=170, scale=1, orientation="front", name="FRONT")
    r = call("add_linear_dimension", view="FRONT", edge_one=horiz[0]["index"], direction="horizontal", x=140, y=100)
    dims = call("list_drawing_dimensions")["dimensions"]
    expect(len(dims) == 1 and near(dims[0]["value_mm"], 100), "dimension listed")
    r = call("set_dimension_tolerance", index=1, upper=0.1, lower=-0.05)
    expect("Deviation" in r.get("tolerance", ""), f"deviation tolerance: {r}")
    call("set_dimension_tolerance", index=1, hole_fit="H7")
    r = call("move_dimension_text", index=1, x=150, y=95)
    at = call("list_drawing_dimensions")["dimensions"][0]["at_mm"]
    expect(at is not None and near(at[0], 150, 0.02), f"dimension text moved: {at}")
    r = call("add_surface_finish", view="FRONT", edge=horiz[0]["index"], roughness="1.6")
    expect(r.get("count") == 1, "surface finish symbol placed")
    r = call("add_hole_table", view="FRONT", x=260, y=200)
    expect(r.get("rows", 0) >= 1, f"hole table rows: {r}")
    r = call("delete_drawing_dimension", index=1)
    expect("deleted" in r and call("list_drawing_dimensions")["count"] == 0, "dimension deleted")
    call("render_sheet", path=os.path.join(OUT, "extras_sheet.png"))
    call("close_document")
    call("create_assembly", name="TbPat")
    call("place_component", path=base, grounded=True)
    call("place_component", path=base, z=50)
    r = call("pattern_component", occurrences=["CovBlock:2"], axis="Z", linear=True, spacing=40, count=3)
    expect(r.get("occurrences") == 4, f"linear pattern makes 3 copies in all: {r.get('occurrences')}")
    r = call("pattern_component", occurrences=["CovBlock:1"], axis="Z", count=4, angle=90)
    expect(r.get("occurrences", 0) >= 7, f"circular pattern adds copies: {r.get('occurrences')}")
    call("close_document")

clean()
print("\nFAILURES:", len(FAIL), flush=True)
for f in FAIL:
    print(" -", f[0], f[1])
    if f[2]:
        print(f[2][-600:])
