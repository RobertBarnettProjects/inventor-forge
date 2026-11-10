"""Live test on a go-kart frame: TAKES OVER THE MOUSE while faces are picked, in a private Inventor process.

Welded 32 x 32 x 3 mm box-section frame as one solid. Rear bearing blocks fixed, front blocks frictionless,
seat load on four pads, engine load on one plate. Then the no-mouse half: copy the study, change its load values,
solve, read the peaks (a linear model must scale with the load), and read reactions from a report.
Also a small plate on a Pin support.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

F = Forge()
OUT = os.path.join(os.path.expanduser("~"), "Documents", "inventor-forge", "kart")
os.makedirs(OUT, exist_ok=True)
FAIL = []


def call(_tool, **args):
    res = F.safe_call(_tool, args)
    print(f"{_tool:24}", json.dumps(res, ensure_ascii=False)[:900], flush=True)
    if not res["ok"]:
        F.safe_call("close_private_inventor", {}) if "--keep" not in sys.argv else None
        raise SystemExit(res.get("error"))
    return res


def check(name, got, want, tol=0.02):
    ok = abs(got - want) <= tol * max(abs(want), 1e-9)
    print(("PASS " if ok else "FAIL ") + f"{name}: {got} (expected {want})", flush=True)
    if not ok:
        FAIL.append(name)


def expect(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + f"{name} {info}", flush=True)
    if not cond:
        FAIL.append(name)


def face(x, y, z, normal):
    return call("find_face", x=x, y=y, z=z, normal=normal)["face"]


call("connect", private=True)
call("create_part", name="KartFrame")
call("create_sketch", plane="XY")
call("draw_closed_profile", points=[[0, -300], [900, -300], [1200, -220], [1200, 220], [900, 300], [0, 300]])
call("draw_closed_profile", points=[[32, -268], [400, -268], [400, 268], [32, 268]])
call("draw_closed_profile", points=[[432, -268], [850, -268], [850, 268], [432, 268]])
call("draw_closed_profile", points=[[882, -268], [895.9, -268], [1168, -195.4], [1168, 195.4], [895.9, 268], [882, 268]])
call("extrude", distance=32, direction="positive")
call("shell", thickness=3)
for x in (255, 705):                      # seat pads on the side rails
    for y in (-284, 284):
        call("create_sketch", plane="XY", offset=32)
        call("draw_rectangle", width=60, height=32, x=x, y=y)
        call("extrude", distance=6, direction="positive")
call("create_sketch", plane="XY", offset=32)   # engine plate on the right rail
call("draw_rectangle", width=120, height=120, x=150, y=240)
call("extrude", distance=6, direction="positive")
blocks = [(80, -284), (80, 284), (1100, -230), (1100, 230)]
for x, y in blocks:                       # axle bearing and stub-axle blocks underneath
    call("create_sketch", plane="XY")
    call("draw_rectangle", width=60, height=30, x=x, y=y)
    call("extrude", distance=50, direction="negative")
call("set_material", name="Steel, Mild")
info = call("inspect")
path = os.path.join(OUT, "KartFrame.ipt")
call("save_document", path=path)
call("screenshot", path=os.path.join(OUT, "frame.png"), view="iso")

rear = [face(80, y, -50, [0, 0, -1]) for y in (-284, 284)]
front = [face(1100, y, -50, [0, 0, -1]) for y in (-230, 230)]
seats = [face(x, y, 38, [0, 0, 1]) for x in (255, 705) for y in (-284, 284)]
engine = face(150, 240, 38, [0, 0, 1])
print("faces", rear, front, seats, engine, flush=True)

SEAT, ENGINE = 2000.0, 600.0
res = call("analyze_stress", fixed_faces=rear, frictionless_faces=front,
           loads=[{"faces": seats, "force": [0, 0, -SEAT]}, {"face": engine, "force": [0, 0, -ENGINE]}],
           study_name="Kart baseline", user_notified=True)
print("\nBASELINE", {k: res.get(k) for k in ("study", "max_von_mises_MPa", "max_displacement_mm", "safety_factor_min", "applied_load_N",
                                            "reaction_N", "equilibrium_error_pct", "solve_seconds", "total_seconds", "solver_warnings")}, flush=True)
print("MOUSE PHASE ONE DONE", flush=True)
expect("study named", "Kart baseline" in res.get("study", ""), res.get("study"))
expect("equilibrium under 1 %", (res.get("equilibrium_error_pct") or 99) < 1, res.get("equilibrium_error_pct"))
call("save_document")

# ---- no mouse from here
studies = call("list_studies")
print(studies["studies"])
params = call("list_analysis_parameters")["parameters"]
base = call("read_result_maximum", study="Kart baseline")
check("colour bar peak matches the report", base["maximum"], res["max_von_mises_MPa"])

copy = call("copy_study", source="Kart baseline", new_name="Kart copy check")
rows = copy["parameters"]
expect("copy has load parameters", len(rows) >= 6, [(p["name"], p["expression"]) for p in rows])
doubled = {}
for p in rows:
    if p["units"] == "N":
        val = float(p["expression"].split()[0])
        doubled[p["name"]] = f"{val * 2:g} N"
call("set_analysis_parameters", values=doubled)
sol = call("solve_study", study="Kart copy check")
two = call("read_result_maximum", study="Kart copy check")
check("double load doubles the stress", two["maximum"], 2 * base["maximum"], 0.02)

values = [(f"{float(p['expression'].split()[0]) * 1.5:g} N" if p["units"] == "N" else None) for p in rows]
out = os.path.join(OUT, "cases.json")
if os.path.exists(out):
    os.remove(out)
run = call("run_study_cases", template="Kart baseline", cases=[{"name": "Heavy driver", "values": values}], results_path=out)
check("case at 1.5x load", run["cases"]["Heavy driver"]["results"]["Von Mises Stress"], 1.5 * base["maximum"], 0.02)
again = call("run_study_cases", template="Kart baseline", cases=[{"name": "Heavy driver", "values": values}], results_path=out)
expect("finished case is skipped on a rerun", again["ran"] == 0 and again["already_done"] == 1, again)

rep = call("study_report", study="Kart copy check")
expect("report reads the named study", rep["study"] == "Kart copy check", rep["study"])
rf = sum((x.get("force_components_N") or [0, 0, 0])[2] or 0 for x in rep["reactions"])
check("copied study carries double the load", abs(rf), 2 * (SEAT + ENGINE), 0.02)
call("screenshot", path=os.path.join(OUT, "result.png"))
call("exit_analysis")

# ---- Pin support, mouse again
print("MOUSE PHASE TWO", flush=True)
call("create_part", name="PinPlate")
call("create_sketch", plane="XY")
call("draw_rectangle", width=100, height=40)
call("extrude", distance=10)
call("hole", x=-30, y=0, diameter=12)
call("set_material", name="Steel, Mild")
hole = [f for f in call("list_faces", type="cylinder")["faces"] if f.get("hole")][0]["index"]
fixed = call("find_face", normal=[1, 0, 0])["face"]
top = call("find_face", normal=[0, 0, 1])["face"]
res = call("analyze_stress", pin_faces=[hole], fixed_faces=[fixed], loads=[{"face": top, "force": [0, 0, -500]}], study_name="Pin check", user_notified=True)
expect("pin support study", (res.get("equilibrium_error_pct") or 99) < 1, res.get("equilibrium_error_pct"))
print("MOUSE PHASE TWO DONE", flush=True)
print("\nFAILED:" if FAIL else "\nALL PASSED", FAIL or "", flush=True)
if "--keep" not in sys.argv:
    F.safe_call("close_private_inventor", {})
