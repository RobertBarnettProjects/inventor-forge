"""Live check of Inventor-native stress analysis against beam theory (TAKES OVER MOUSE + KEYBOARD).

150 x 20 x 10 mm mild-steel cantilever (E 220 GPa), 200 N tip load in -Z:
sigma = 6PL/(b h^2) = 90 MPa, tip deflection = PL^3 / 3EI = 0.6136 mm.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

F = Forge()


def call(_tool, **args):
    res = F.safe_call(_tool, args)
    print(f"{_tool:18}", json.dumps(res, ensure_ascii=False)[:1200])
    if not res["ok"]:
        raise SystemExit(res.get("error"))
    return res


call("create_part", name="ForgeCantilever")
call("create_sketch", plane="YZ")
call("draw_rectangle", width=20, height=10)
call("extrude", distance=150)
call("set_material", name="Steel, Mild")
root = call("find_face", normal=[-1, 0, 0])["face"]
tip = call("find_face", normal=[1, 0, 0])["face"]
res = call("analyze_stress", fixed_faces=[root], loads=[{"face": tip, "force": [0, 0, -200]}], user_notified=True)
print(f"\nINVENTOR: vM {res['max_von_mises_MPa']} MPa (theory 90), deflection {res['max_displacement_mm']} mm "
      f"(theory 0.6136), SF {res.get('safety_factor_min')}, equilibrium {res.get('equilibrium_error_pct')} %")
if "--fine" in sys.argv:
    res2 = call("analyze_stress", fixed_faces=[root], loads=[{"face": tip, "force": [0, 0, -200]}], mesh_fraction=0.04, user_notified=True)
    print(f"FINE: vM {res2['max_von_mises_MPa']} MPa, deflection {res2['max_displacement_mm']} mm")
if "--modal" in sys.argv:
    m = call("analyze_modes", fixed_faces=[root], modes=3, user_notified=True)
    print("MODES", m["frequencies_Hz"])
