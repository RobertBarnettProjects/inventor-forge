"""Live checks of the less common analysis paths (TAKES OVER MOUSE + KEYBOARD).
Pressure, gravity, several fixed faces, a curved (hole) face, requested mode count. Mild steel, E 220 GPa.
    python -X utf8 tests/smoke_fea2.py [pressure gravity twofixed hole modes]
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

F = Forge()
FAIL = []
which = sys.argv[1:] or ["pressure", "gravity", "twofixed", "hole", "modes"]


def call(_tool, **args):
    res = F.safe_call(_tool, args)
    print(f"{_tool:18}", json.dumps(res, ensure_ascii=False)[:520], flush=True)
    if not res["ok"]:
        FAIL.append((_tool, res.get("error"), res.get("trace", "")))
    return res


def expect(cond, msg):
    print(("   OK  " if cond else "   BAD ") + msg, flush=True)
    if not cond:
        FAIL.append(("expect", msg, ""))


def near(a, b, rel):
    return a is not None and abs(a - b) <= rel * abs(b)


def bar(name):
    for d in F.safe_call("list_documents").get("documents", []):
        if d["name"].startswith("Fea"):
            F.safe_call("close_document", {"name": d["name"]})
    call("create_part", name=name)
    call("create_sketch", plane="YZ")
    call("draw_rectangle", width=20, height=10)
    call("extrude", distance=150)
    call("set_material", name="Steel, Mild")
    return call("find_face", normal=[-1, 0, 0])["face"], call("find_face", normal=[1, 0, 0])["face"], call("find_face", normal=[0, 0, 1])["face"]


if "pressure" in which:
    print("\n== pressure: 0.1 MPa on the 150 x 20 top face of a cantilever", flush=True)
    root, tip, top = bar("FeaPressure")
    r = call("analyze_stress", fixed_faces=[root], loads=[{"face": top, "pressure": 0.1}], mesh_fraction=0.05, user_notified=True)
    expect(near((r.get("reaction_N") or [0, 0, 0])[2], 300, 0.01), f"reaction {r.get('reaction_N')} vs 300 N up (0.1 MPa x 3000 mm2)")
    expect(r.get("equilibrium_error_pct", 99) < 1, f"equilibrium {r.get('equilibrium_error_pct')} %")
    expect(near(r.get("max_displacement_mm"), 0.345, 0.05), f"deflection {r.get('max_displacement_mm')} vs wL^4/8EI 0.345 mm")
    expect(near(r.get("max_von_mises_MPa"), 67.5, 0.12), f"stress {r.get('max_von_mises_MPa')} vs 67.5 MPa")

if "gravity" in which:
    print("\n== gravity only", flush=True)
    root, tip, top = bar("FeaGravity")
    r = call("analyze_stress", fixed_faces=[root], gravity=True, user_notified=True)
    expect(near((r.get("reaction_N") or [0, 0, 0])[2], 0.2355 * 9.81, 0.02), f"reaction {r.get('reaction_N')} vs weight 2.31 N")
    expect(r.get("equilibrium_error_pct", 99) < 2, f"equilibrium {r.get('equilibrium_error_pct')} %")

if "twofixed" in which:
    print("\n== two fixed faces: beam fixed at both ends, 1000 N spread over the top", flush=True)
    root, tip, top = bar("FeaTwoFixed")
    r = call("analyze_stress", fixed_faces=[root, tip], loads=[{"face": top, "force": [0, 0, -1000]}], mesh_fraction=0.05, user_notified=True)
    expect(near((r.get("reaction_N") or [0, 0, 0])[2], 1000, 0.01), f"reaction {r.get('reaction_N')} vs 1000 N")
    expect(0.022 <= (r.get("max_displacement_mm") or 0) <= 0.035, f"mid deflection {r.get('max_displacement_mm')} vs wL^4/384EI 0.024 mm (+ shear)")

if "hole" in which:
    print("\n== curved face: plate fixed by the wall of a hole", flush=True)
    for d in F.safe_call("list_documents").get("documents", []):
        if d["name"].startswith("Fea"):
            F.safe_call("close_document", {"name": d["name"]})
    call("create_part", name="FeaHole")
    call("create_sketch", plane="XY")
    call("draw_rectangle", width=100, height=40)
    call("extrude", distance=8)
    call("hole", x=-30, y=0, diameter=12)
    call("set_material", name="Steel, Mild")
    hole = [f for f in call("list_faces", type="cylinder")["faces"] if f.get("hole")][0]["index"]
    tip = call("find_face", normal=[1, 0, 0])["face"]
    r = call("analyze_stress", fixed_faces=[hole], loads=[{"face": tip, "force": [0, 0, -50]}], user_notified=True)
    expect(near((r.get("reaction_N") or [0, 0, 0])[2], 50, 0.01), f"reaction {r.get('reaction_N')} vs 50 N")
    expect((r.get("moment_check") or {}).get("ok") is True, f"moment about the hole: {r.get('moment_check')} (50 N x 80 mm = 4 N m)")

if "modes" in which:
    print("\n== requested mode count", flush=True)
    root, tip, top = bar("FeaModes")
    r = call("analyze_modes", fixed_faces=[root], modes=3, user_notified=True)
    print("   all", r.get("all_frequencies_Hz"), flush=True)
    expect(len(r.get("all_frequencies_Hz", [])) == 3, "Inventor solved exactly the requested number of modes")
    expect(near((r.get("frequencies_Hz") or [0])[0], 380, 0.03), f"first mode {r.get('frequencies_Hz')} vs 380 Hz")

print("\nFAILURES:", len(FAIL), flush=True)
for f in FAIL:
    print(" -", f[0], f[1])
