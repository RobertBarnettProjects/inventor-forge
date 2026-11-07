"""Live smoke test: build a flanged plate with holes in Inventor and check every delta.

Run: python -X utf8 tests/smoke_part.py   (Inventor must be installed; it is started if needed)
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

F = Forge()
FAIL = []


def call(_tool, **args):
    name = _tool
    res = F.safe_call(name, args)
    short = {k: v for k, v in res.items() if k in ("ok", "delta", "error", "feature", "warning")}
    print(f"{name:22} {json.dumps(short, ensure_ascii=False)[:300]}")
    if not res["ok"]:
        FAIL.append((name, res.get("error"), res.get("trace", "")))
    return res


def approx(a, b, rel=1e-3):
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-9)


call("connect")
call("create_part", name="ForgeSmokePlate")
call("create_sketch", plane="XY")
call("draw_rectangle", width=120, height=80)
res = call("extrude", distance=10)
assert approx(res["volume_mm3"], 120 * 80 * 10), res
res = call("hole", points=[[-40, -25], [40, -25], [-40, 25], [40, 25]], diameter=11)
exp = 120 * 80 * 10 - 4 * math.pi * 5.5 ** 2 * 10
assert approx(res["volume_mm3"], exp), (res, exp)
res = call("hole", x=0, y=0, tap="M12x1.75", depth=0)
res = call("find_edge", x=60, y=0, z=10)
e = res.get("edge")
res = call("fillet", radius=3, edges=[e]) if e else None
res = call("list_faces", type="cylinder")
print("  cylinders:", [(f["index"], f["diameter_mm"], f["hole"]) for f in res.get("faces", [])])
res = call("find_face", normal=[0, 0, 1])
print("  top face:", res.get("face"), res.get("match", {}).get("centroid_mm"))
call("set_material", name="Steel, Mild")
res = call("mass_properties")
print("  mass:", res.get("mass_kg"), "cog", res.get("cog_mm"), "rho", res.get("density_kg_m3"))
call("inspect")
call("list_features")
call("get_parameters")
call("list_dimensions")
res = call("edit_dimension", parameter="d0", value="140 mm")
call("set_iproperties", properties={"part_number": "FS-001", "description": "Smoke test plate", "designer": "forge"})
call("get_iproperties")
call("screenshot", view="iso")
call("export_document", path="forge_smoke.stp")
print("\nFAILURES:", len(FAIL))
for f in FAIL:
    print(" -", f[0], f[1])
    if f[2]:
        print(f[2])
call("close_document", save=False)
print("\nFAILURES:", len(FAIL))
