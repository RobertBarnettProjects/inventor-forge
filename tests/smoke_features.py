"""Live coverage of the less common tools: a pipe flange (revolve, bolt circle via circular pattern,
counterbores, chamfer, thread), a pocketed block (rectangular pattern, mirror, shell, slot, polygon),
sweep, loft, work planes, measure, undo/transactions, section + detail views, manual dimensions."""
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
    print(f"{_tool:22}", json.dumps(res, ensure_ascii=False)[:420])
    if not res["ok"]:
        FAIL.append((_tool, res.get("error"), res.get("trace", "")))
    return res


def near(a, b, rel=2e-3):
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-9)


def expect(cond, msg):
    print(("   OK  " if cond else "   BAD ") + msg)
    if not cond:
        FAIL.append(("expect", msg, ""))


# ---------------------------------------------------------------- flange
print("\n== flange")
call("create_part", name="ForgeFlange")
call("create_sketch", plane="XZ")
# half cross-section in the XZ sketch (sketch x = radius, sketch y = height); revolve about Z
call("draw_closed_profile", points=[[20, 0], [75, 0], [75, 16], [35, 16], [35, 40], [20, 40]])
ax = call("sketch_info")
r = call("revolve", axis="Z")
v_exp = math.pi * (75 ** 2 - 20 ** 2) * 16 + math.pi * (35 ** 2 - 20 ** 2) * 24
expect(near(r.get("volume_mm3", 0), v_exp), f"revolve volume {r.get('volume_mm3')} vs {v_exp:.0f}")
h = call("hole", x=55, y=0, diameter=14, cbore_diameter=22, cbore_depth=4)
call("list_features")
p = call("circular_pattern", features=[h.get("feature", "Hole1")], count=6, axis="Z")
cb = math.pi * 7 ** 2 * 16 + math.pi * (11 ** 2 - 7 ** 2) * 4
expect(near(p.get("volume_change_mm3", 0), -5 * cb, 5e-3), f"pattern removed {p.get('volume_change_mm3')} vs {-5 * cb:.0f}")
top_edge = call("find_edge", x=35, y=0, z=40, type="circle")
call("chamfer", distance=1.5, edges=[top_edge["edge"]])
bore = [f for f in call("list_faces", type="cylinder")["faces"] if f.get("hole") and abs(f["diameter_mm"] - 40) < 0.01]
expect(bool(bore), "bore face found")
if bore:
    call("thread", face_index=bore[0]["index"], designation="M40x3", internal=True, length=20)
call("set_material", name="Steel, Mild")
call("mass_properties")
d = call("measure", face_one=call("find_face", normal=[0, 0, 1], z=16)["face"],
         face_two=call("find_face", normal=[0, 0, -1])["face"])
expect(near(d.get("min_distance_mm", 0), 16), f"flange thickness {d.get('min_distance_mm')}")
call("set_iproperties", properties={"part_number": "FF-080", "description": "Weld-neck flange DN40 (test)"})
call("save_document", path=os.path.join(OUT, "ForgeFlange.ipt"))
call("screenshot", path=os.path.join(OUT, "flange_iso.png"), view="iso")

print("\n== flange drawing: section + detail + manual dims")
call("make_part_sheet", model=os.path.join(OUT, "ForgeFlange.ipt"), views="front,top,iso")
lv = call("list_views")
front = [v for v in lv["views"] if v["name"] == "FRONT"][0]
call("add_section_view", parent="FRONT", x=front["center_mm"][0], y=245,
     cut="horizontal", label="A")
call("add_detail_view", parent="FRONT", center_x=front["center_mm"][0] + 27.5, center_y=front["center_mm"][1],
     radius=12, x=330, y=120, scale=2, label="B")
qa = call("check_drawing")
expect(not any("overlap" in i for i in qa.get("issues", [])), f"no overlaps after placing section/detail: {qa.get('issues')}")
call("render_sheet", path=os.path.join(OUT, "flange_sheet.png"))
call("close_document")

# ---------------------------------------------------------------- block
print("\n== pocketed block")
call("activate_document", name="ForgeFlange")
call("close_document")
call("create_part", name="ForgeBlock")
call("create_sketch", plane="XY")
call("draw_rectangle", width=100, height=60, x=0, y=0, centered=False)
call("extrude", distance=20)
call("create_sketch", plane="XY", offset=20)
call("draw_slot", length=20, width=8, x=15, y=15)
s1 = call("extrude", distance=5, operation="cut")
slot_v = (20 * 8 + math.pi * 16) * 5
expect(near(-s1.get("volume_change_mm3", 0), slot_v), f"slot pocket {s1.get('volume_change_mm3')} vs {-slot_v:.1f}")
call("rectangular_pattern", features=[s1["feature"]], x_count=3, x_spacing=30, y_count=2, y_spacing=30)
call("create_sketch", plane="XZ")
call("draw_polygon", sides=6, radius=6, x=-50, y=10, inscribed=False)   # XZ sketch x = model -X
hx = call("extrude", distance=200, operation="cut", direction="symmetric")
expect(hx.get("volume_change_mm3", 0) < -1000, f"hex cut removed {hx.get('volume_change_mm3')}")
call("work_plane", base="YZ", offset=50, name="Mid")
call("mirror", features=[s1["feature"]], plane="Mid")
call("transaction", action="begin", name="trial")
call("fillet", radius=2, edges=[call("find_edge", x=0, y=0, z=10)["edge"]])
ab = call("transaction", action="abort")
expect(abs(ab.get("volume_change_mm3", 1)) > 0, "abort rolled back the fillet")
before = call("inspect")["volume_mm3"]
call("shell", thickness=3, remove_faces=[call("find_face", normal=[0, 0, -1])["face"]])
call("undo")
expect(near(call("inspect")["volume_mm3"], before), "undo restored the shell")
call("suppress_feature", feature=hx["feature"])
call("suppress_feature", feature=hx["feature"], suppress=False)
call("close_document")

# ---------------------------------------------------------------- sweep + loft
print("\n== sweep / loft")
call("create_part", name="ForgeSweepLoft")
call("create_sketch", plane="XY")
call("draw_line", x1=0, y1=0, x2=100, y2=0)
call("create_sketch", plane="YZ")
call("draw_circle", diameter=10)
sw = call("sweep", profile_sketch=2, path_sketch=1)
expect(near(sw.get("volume_mm3", 0), math.pi * 25 * 100), f"sweep volume {sw.get('volume_mm3')}")
call("create_sketch", plane="XY", offset=120)
call("draw_rectangle", width=40, height=40)
call("create_sketch", plane="XY", offset=180)
call("draw_circle", diameter=20)
call("loft", sketches=[3, 4], operation="new_body")
call("inspect")
call("close_document")

print("\nFAILURES:", len(FAIL))
for f in FAIL:
    print(" -", f[0], f[1])
    if f[2]:
        print(f[2][-800:])
