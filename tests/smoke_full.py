"""Live test of the analysis and drawing additions, in a private Inventor. TAKES OVER THE MOUSE in parts A-C.

A  cantilever: value at a point vs beam theory, mesh convergence, batch run that survives an Inventor crash
B  kart frame: several faces from one view, remote force, moment, local mesh, Inventor's own refinement,
   single-study report
C  assembly: automatic contacts, changing a contact to Separation, model state, bearing load on a pin plate
D  drawings (no mouse): long part turned, cross-hole section, spline hole, cosmetic thread, tilted part, GA sheet size
Run one part: python tests/smoke_full.py A
"""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge import uidrive as U  # noqa: E402
from inventor_forge.engine import Forge  # noqa: E402

F = Forge()
HOME = os.path.join(os.path.expanduser("~"), "Documents", "inventor-forge", "full")
os.makedirs(HOME, exist_ok=True)
FAIL = []
parts = sys.argv[1:] or ["A", "B", "C", "D"]
RUN = time.strftime("%H%M")


def call(_tool, **args):
    t0 = time.time()
    res = F.safe_call(_tool, args)
    print(f"{_tool:24} {time.time() - t0:6.1f}s", json.dumps(res, ensure_ascii=False)[:700], flush=True)
    if not res["ok"]:
        FAIL.append(f"{_tool}: {res.get('error')}")
        raise RuntimeError(res.get("error"))
    return res


def check(name, got, want, tol):
    ok = got is not None and abs(got - want) <= tol
    print(("PASS " if ok else "FAIL ") + f"{name}: {got} (expected {want} ± {tol})", flush=True)
    if not ok:
        FAIL.append(name)


def expect(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + f"{name} {str(info)[:300]}", flush=True)
    if not cond:
        FAIL.append(name)


def face(**kw):
    return call("find_face", **kw)["face"]


def asm_face(occ, normal, near=None):
    rows = call("inspect_assembly", faces_of=occ)["faces"]
    rows = [r for r in rows if r.get("normal") and sum(r["normal"][i] * normal[i] for i in range(3)) > 0.999]
    if near:
        rows.sort(key=lambda r: sum((r["centroid_mm"][i] - near[i]) ** 2 for i in range(3)))
    else:
        rows.sort(key=lambda r: -sum(r["centroid_mm"][i] * normal[i] for i in range(3)))
    return f"{occ}/{rows[0]['index']}"


def section(name, fn):
    print(f"\n===== {name}", flush=True)
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        print("SECTION STOPPED:", e, flush=True)
        FAIL.append(f"{name} stopped: {e}")


def part_a():
    call("create_part", name="Cantilever")
    call("create_sketch", plane="YZ")
    call("draw_rectangle", width=20, height=10)
    call("extrude", distance=150)
    call("set_material", name="Steel, Mild")
    root, tip, top = face(normal=[-1, 0, 0]), face(normal=[1, 0, 0]), face(normal=[0, 0, 1])
    path = os.path.join(HOME, f"Cantilever_{time.strftime('%H%M%S')}.ipt")
    call("save_document", path=path)
    r = call("analyze_stress", fixed_faces=[root], loads=[{"face": tip, "force": [0, 0, -200]}], mesh_fraction=0.05,
             study_name="Beam", user_notified=True)
    expect("beam equilibrium", (r.get("equilibrium_error_pct") if r.get("equilibrium_error_pct") is not None else 99) < 1, r.get("equilibrium_error_pct"))
    call("save_document")
    # deflection at mid-span, beam theory: P x^2 (3L - x) / (6 E I) = 0.192 mm (tip 0.614 mm)
    v = call("result_at_point", study="Beam", face=top, point=[75, 0, 5], result="Displacement", tolerance=0.004,
             user_notified=True)
    check("deflection at mid-span vs beam theory", v["value"], 0.192, 0.012)
    v = call("result_at_point", study="Beam", face=top, point=[75, 0, 5], tolerance=1, user_notified=True)
    check("stress at mid-span vs bending theory", v["value"], 45.0, 3.0)
    m = call("mesh_convergence", study="Beam", fractions=[0.1, 0.05])
    expect("convergence table", len(m["runs"]) == 2 and m["last_change_pct"] is not None, m)
    call("save_document")
    base = call("read_result_maximum", study="Beam")["maximum"]
    rows = call("copy_study", source="Beam", new_name="Beam probe")["parameters"]
    call("delete_study_item", study="Beam probe")
    call("save_document")
    n = len(rows)
    values = [("-400 N" if p["expression"].strip().startswith("-200") else None) for p in rows]
    out = os.path.join(HOME, "beam_cases.json")
    if os.path.exists(out):
        os.remove(out)
    r = call("run_study_cases", template="Beam", cases=[{"name": "Double", "values": values}], results_path=out)
    check("double load doubles the peak", r["cases"]["Double"]["results"]["Von Mises Stress"], 2 * base, 0.03 * 2 * base)
    print("parameters in copy:", n, flush=True)


def part_b():
    call("open_document", path=os.path.expanduser(r"~\Documents\inventor-forge\kart\KartFrame.ipt"))
    rear = [face(x=80, y=y, z=-50, normal=[0, 0, -1]) for y in (-284, 284)]
    front = [face(x=1100, y=y, z=-50, normal=[0, 0, -1]) for y in (-230, 230)]
    seats = [face(x=x, y=y, z=38, normal=[0, 0, 1]) for x in (255, 705) for y in (-284, 284)]
    engine = face(x=150, y=240, z=38, normal=[0, 0, 1])
    tow = face(x=0, y=0, z=16, normal=[-1, 0, 0])
    t0 = time.time()
    r = call("analyze_stress", fixed_faces=rear, frictionless_faces=front, study_name=f"Kart full {RUN}",
             loads=[{"faces": seats, "force": [0, 0, -2000]}, {"face": engine, "moment": [0, 50, 0]},
                    {"face": tow, "remote_force": [-300, 0, 0], "point": [-150, 0, 16]}],
             local_mesh=[{"faces": seats, "size": 6}], refinements=2, user_notified=True)
    print("kart full took", round(time.time() - t0), "s", flush=True)
    expect("kart equilibrium with remote force", (r.get("equilibrium_error_pct") if r.get("equilibrium_error_pct") is not None else 99) < 1,
           (r.get("applied_load_N"), r.get("reaction_N"), r.get("equilibrium_error_pct")))
    call("save_document")
    rep = call("study_report", study=f"Kart full {RUN}", only_this_study=True, user_notified=True)
    text = open(rep["report"], encoding="utf-8", errors="replace").read()
    expect("single-study report", f"Kart full {RUN}" in text and "Kart baseline" not in text, rep["report"])
    expect("single-study report holds the set-up", len(rep["loads"]) >= 3, rep.get("note"))
    full = call("study_report", study=f"Kart full {RUN}")
    expect("full report has the reactions", len(full["reactions"]) >= 2, full["reactions"])
    # a batch that survives its Inventor going away: this session's private Inventor exits during the first case
    out = os.path.join(HOME, "kart_restart.json")
    if os.path.exists(out):
        os.remove(out)
    os.environ["INVENTOR_FORGE_TEST_EXIT_AT"] = f"Restart A {RUN}"
    r = call("run_study_cases", template="Kart baseline", results_path=out,
             cases=[{"name": f"Restart A {RUN}", "values": [None, None, "-2400 N", None, None, None]},
                    {"name": f"Restart B {RUN}", "values": [None, None, "-2800 N", None, None, None]}])
    expect("batch carried on after Inventor exited", r["inventor_restarts"] == 1 and r["ran"] == 2, r)
    call("exit_analysis")
    call("close_document", save=False)


def part_c():
    call("open_document", path=os.path.expanduser(r"~\Documents\inventor-forge\asm\Stack.iam"))
    bottom = asm_face("Base:1", [0, 0, -1])
    top = asm_face("Beam:1", [0, 0, 1])
    r = call("analyze_stress", fixed_faces=[bottom], loads=[{"face": top, "force": [0, 0, -1000]}], gravity=True,
             study_name="Stack bonded", contact_type="Bonded", user_notified=True)
    expect("assembly contact found", bool(r.get("contacts")), r.get("contacts"))
    expect("assembly equilibrium (with weight)", (r.get("equilibrium_error_pct") if r.get("equilibrium_error_pct") is not None else 99) < 1,
           (r.get("applied_load_N"), r.get("reaction_N")))
    r2 = call("analyze_stress", fixed_faces=[bottom], loads=[{"face": top, "force": [0, 0, -1000]}],
              study_name="Stack separation", contacts=[{"between": ["Base:1", "Beam:1"], "type": "Separation"}],
              model_state="Variant B", user_notified=True)
    expect("contact changed to Separation", any(c["type"] == "Separation" for c in r2.get("contacts", [])), r2.get("contacts"))
    expect("separation equilibrium", (r2.get("equilibrium_error_pct") if r2.get("equilibrium_error_pct") is not None else 99) < 1, r2.get("equilibrium_error_pct"))
    call("set_contact_type", study="Stack separation", between=["Base:1"], type="Bonded")
    call("exit_analysis")
    call("close_document", save=False)
    # bearing load on a pin plate
    call("create_part", name="LugPlate")
    call("create_sketch", plane="XY")
    call("draw_rectangle", width=100, height=40)
    call("extrude", distance=10)
    call("hole", x=-30, y=0, diameter=12)
    call("set_material", name="Steel, Mild")
    hole = [f for f in call("list_faces", type="cylinder")["faces"] if f.get("hole")][0]["index"]
    fixed = call("find_face", normal=[1, 0, 0])["face"]
    r3 = call("analyze_stress", fixed_faces=[fixed], loads=[{"face": hole, "bearing": [0, -500, 0]}], study_name="Lug bearing",
              user_notified=True)
    expect("bearing load equilibrium", (r3.get("equilibrium_error_pct") if r3.get("equilibrium_error_pct") is not None else 99) < 1, (r3.get("applied_load_N"), r3.get("reaction_N")))
    call("exit_analysis")
    call("close_document", save=False)


def part_d():
    # long round bar along Y: turned to lie down; a cross hole along X gets a section; a hole along Z shows as a spline
    call("create_part", name="Shaft")
    call("create_sketch", plane="XZ")
    call("draw_circle", diameter=30)
    call("extrude", distance=200, direction="negative")
    lo = call("inspect")["bbox_min_mm"]
    print("shaft bbox min", lo, flush=True)
    y0 = lo[1]
    call("execute_python", code="sk=cdef.Sketches.Add(cdef.WorkPlanes.Item(3))\n"
                                f"sk.SketchCircles.AddByCenterRadius(sk.ModelToSketchSpace(tg.CreatePoint(0,{(y0 + 50) / 10},0)), 0.4)\n"
                                "p=sk.Profiles.AddForSolid()\n"
                                "d=cdef.Features.ExtrudeFeatures.CreateExtrudeDefinition(p, K.kCutOperation)\n"
                                "d.SetThroughAllExtent(K.kSymmetricExtentDirection)\n"
                                "cdef.Features.ExtrudeFeatures.Add(d)")
    call("execute_python", code="sk=cdef.Sketches.Add(cdef.WorkPlanes.Item(1))\n"
                                f"sk.SketchCircles.AddByCenterRadius(sk.ModelToSketchSpace(tg.CreatePoint(0,{(y0 + 150) / 10},0)), 0.5)\n"
                                "p=sk.Profiles.AddForSolid()\n"
                                "d=cdef.Features.ExtrudeFeatures.CreateExtrudeDefinition(p, K.kCutOperation)\n"
                                "d.SetThroughAllExtent(K.kSymmetricExtentDirection)\n"
                                "cdef.Features.ExtrudeFeatures.Add(d)")
    call("set_material", name="Steel, Mild")
    shaft = os.path.join(HOME, "Shaft.ipt")
    call("save_document", path=shaft)
    r = call("make_part_sheet", model=shaft, title="SHAFT", drawing_number="SH-1", drawn_by="RB")
    expect("long part turned", r.get("rotated") is True, r)
    expect("cross hole sectioned", r.get("section") == "A-A", r.get("section"))
    expect("spline hole called out", (r.get("callouts") or {}).get("leader_notes", 0) >= 1, r.get("callouts"))
    call("render_sheet", path=os.path.join(HOME, "shaft_sheet.png"))
    call("save_document", path=os.path.join(HOME, "Shaft.idw"))
    call("close_document", save=False)
    # plate with a cosmetic thread in a plain hole
    call("create_part", name="ThreadPlate")
    call("create_sketch", plane="XY")
    call("draw_rectangle", width=100, height=60)
    call("extrude", distance=10)
    call("create_sketch", plane="XY", offset=10)
    call("draw_circle", diameter=8.376, x=20, y=0)
    call("extrude", through_all=True, operation="cut")
    bore = [f for f in call("list_faces", type="cylinder")["faces"] if f.get("hole")][0]["index"]
    call("thread", face_index=bore, designation="M10x1.5", internal=True)
    tp = os.path.join(HOME, "ThreadPlate.ipt")
    call("save_document", path=tp)
    r = call("make_part_sheet", model=tp, title="THREAD PLATE", drawing_number="TP-1", drawn_by="RB")
    print("thread callouts", r.get("callouts"), flush=True)
    call("render_sheet", path=os.path.join(HOME, "thread_sheet.png"))
    call("close_document", save=False)
    # tilted solid (as an imported STEP part would be)
    call("create_part", name="Tilted")
    call("execute_python", code="tb=app.TransientBRep\nbx=tg.CreateBox()\nbx.MinPoint=tg.CreatePoint(0,0,0)\nbx.MaxPoint=tg.CreatePoint(12,6,1)\n"
                                "b=tb.CreateSolidBlock(bx)\nm=tg.CreateMatrix()\nm.SetToRotation(0.5,tg.CreateVector(1,0,0),tg.CreatePoint(0,0,0))\n"
                                "m2=tg.CreateMatrix()\nm2.SetToRotation(0.35,tg.CreateVector(0,0,1),tg.CreatePoint(0,0,0))\nm.PreMultiplyBy(m2)\n"
                                "tb.Transform(b,m)\ncdef.Features.NonParametricBaseFeatures.Add(b)")
    tilt = os.path.join(HOME, "Tilted.ipt")
    call("save_document", path=tilt)
    r = call("make_part_sheet", model=tilt, title="TILTED", drawing_number="TL-1", drawn_by="RB")
    expect("tilted part straightened", "tilted_part" in r, r)
    call("render_sheet", path=os.path.join(HOME, "tilted_sheet.png"))
    call("close_document", save=False)
    # GA sheet size
    r = call("make_assembly_sheet", model=os.path.expanduser(r"~\Documents\inventor-forge\asm\Stack.iam"), sheet_size="auto",
             title="STACK", drawing_number="ST-1", drawn_by="RB")
    expect("GA sheet chosen", r.get("sheet") in ("A3", "A2", "A1"), r.get("sheet"))
    call("render_sheet", path=os.path.join(HOME, "ga_sheet.png"))
    call("close_document", save=False)


try:
    call("connect", private=True)
    for p, fn in (("A", part_a), ("B", part_b), ("C", part_c), ("D", part_d)):
        if p in parts:
            section(p, fn)
            F.safe_call("close_unused_documents", {})
finally:
    print("\nFAILED:" if FAIL else "\nALL PASSED", json.dumps(FAIL, indent=1) if FAIL else "", flush=True)
    F.safe_call("close_private_inventor", {})
