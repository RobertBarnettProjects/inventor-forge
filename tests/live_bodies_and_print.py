"""Live: session pinning and start-up checks, multi-body targets, selections, parametric profiles, batches, poses,
framed screenshots that keep the saved state, the print package, parameter knock-on reports, renames, display scope,
split-face fallbacks. Private Inventor only; it is closed at the end. No mouse or keyboard.

    python tests/live_bodies_and_print.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

F = Forge(visible=False)
FAIL = []
work = tempfile.mkdtemp(prefix="forge-bodies-")


def call(_tool, **a):
    r = F.safe_call(_tool, a)
    print(f"{_tool:22}", json.dumps(r, default=str)[:400], flush=True)
    return r


def expect(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + f"{name} {info}", flush=True)
    if not cond:
        FAIL.append(name)


try:
    r = call("connect", private=True)
    expect("private connect pinned", r["ok"] and r.get("pinned") == r.get("process"), str(r.get("checks", "")))
    expect("start lock released", os.path.exists(os.path.join(tempfile.gettempdir(), "inventor_forge_start.lock")))

    # ---- two bodies: a rotor block and a stator block
    call("create_part", name="TwoBodies")
    call("add_parameter", name="Len", expression="40 mm")
    call("create_sketch", plane="XY")
    call("draw_rectangle", width=40, height=20, x=0, y=0)
    call("extrude", distance=10)
    call("create_sketch", plane="XY")
    call("draw_rectangle", width=20, height=20, x=50, y=0)
    r = call("extrude", distance=10, operation="new_body")
    b = call("list_bodies")
    names = [x["name"] for x in b.get("bodies", [])]
    expect("two bodies listed with names", b["ok"] and len(names) == 2, str(names))
    r = call("rename", kind="body", target="2", new_name="Stator")
    expect("body rename read back", r["ok"] and r.get("to") == "Stator", r.get("error", ""))
    r = call("rename", kind="body", target="1", new_name="Stator")
    expect("duplicate body name refused", not r["ok"], r.get("error", "")[:160])

    # cut a hole through the stator only: sketch over the stator
    call("create_sketch", plane="XY", offset=10)
    call("draw_circle", diameter=6, x=50, y=0)
    r = call("extrude", operation="cut", through_all=True, body="Stator")
    ch = r.get("bodies_changed", {})
    expect("cut on named body changes only it", r["ok"] and "Stator" in ch and len(ch) == 1, json.dumps(ch))
    # a cut aimed at the other body changes nothing and must be refused
    call("create_sketch", plane="XY", offset=10)
    call("draw_circle", diameter=4, x=55, y=5)
    r = call("extrude", operation="cut", through_all=True, body=names[0])
    err = r.get("error", "")
    expect("cut that misses its named body refused", not r["ok"] and ("changed nothing" in err or "doesn't reach" in err),
           r.get("error", "")[:200])

    r = call("select_edges", plane={"axis": "z", "at": 10}, type="line", body="Stator", samples=1)
    expect("select_edges top of stator gives 4 lines", r["ok"] and r.get("count") == 4, str(r.get("edges")))
    r2 = call("fillet", radius=1, edges=r.get("edges", [])[:1], body="Stator")
    expect("fillet on named body", r2["ok"] and "Stator" in (r2.get("bodies_changed") or {}), r2.get("error", ""))
    r = call("find_edge", x=50, y=0, z=10, type="circle", body="all")
    expect("find_edge searches every body", r["ok"] and r.get("body") == "Stator", str(r.get("body")))
    r = call("find_edge", x=500, y=0, z=0, strict=True, tolerance=0.5)
    expect("strict find_edge refuses a far match", not r["ok"] and "no edge within" in r.get("error", ""))
    r = call("body_gap", body_one=names[0], body_two="Stator")
    expect("body gap 20 mm", r["ok"] and abs((r.get("gap_mm") or 0) - 20) < 0.01, str(r.get("gap_mm")))

    r = call("hole", points=[[0, 0], [200, 0]], diameter=3, body=names[0])
    expect("hole centre off its face refused", not r["ok"] and "don't lie on" in r.get("error", ""), r.get("error", "")[:160])

    # ---- poses: move the stator onto the rotor (a clash), with a picture; the part must not change
    v0 = call("inspect").get("volume_mm3")
    r = call("pose_bodies", moves=[{"body": "Stator", "translate": [-35, 0, 0]}],
             path=os.path.join(work, "pose.png"), view="iso")
    expect("pose finds the clash", r["ok"] and r.get("clashes"), json.dumps(r.get("pairs", ""))[:200])
    expect("pose picture written", r["ok"] and os.path.exists((r.get("picture") or {}).get("path", "")))
    expect("pose leaves the part alone", call("inspect").get("volume_mm3") == v0)

    # ---- parameter knock-on report
    p = os.path.join(work, "TwoBodies.ipt")
    call("save_document", path=p)
    r = call("save_document", path=p)
    expect("same-path save goes in place", r["ok"] and r.get("saved", "").lower() == p.lower(), r.get("error", ""))
    r = call("set_parameter", name="Len", expression="45 mm")
    expect("set_parameter reports changes list", r["ok"] and "changed" in r, "")

    # ---- screenshot keeps the saved state, framing
    call("save_document")
    r = call("screenshot", path=os.path.join(work, "shot.png"), view="iso", up="z", target="Stator", field_mm=40)
    d = call("status").get("active", {}).get("dirty")
    expect("screenshot keeps the document clean", r["ok"] and d is False, f"dirty={d}")
    r = call("set_display", mode="shaded_edges", scope="view")
    expect("display mode set on the view", r["ok"] and r.get("view") == "shaded_edges", json.dumps(r)[:200])

    # ---- batch: success, then a failing step rolls everything back
    v1 = call("inspect").get("volume_mm3")
    r = call("batch", steps=[{"tool": "create_sketch", "args": {"plane": "XY", "offset": 10}},
                             {"tool": "draw_circle", "args": {"diameter": 5, "x": 10, "y": 0}},
                             {"tool": "extrude", "as": "pocket", "args": {"operation": "cut", "distance": 3,
                                                                          "body": names[0]}}])
    expect("batch runs", r["ok"] and len(r.get("steps", [])) == 3, r.get("error", "")[:200])
    v2 = call("inspect").get("volume_mm3")
    r = call("batch", steps=[{"tool": "create_sketch", "args": {"plane": "XY", "offset": 10}},
                             {"tool": "draw_circle", "args": {"diameter": 5, "x": -10, "y": 0}},
                             {"tool": "extrude", "args": {"operation": "cut", "distance": 3}},
                             {"tool": "fillet", "args": {"radius": 50, "edges": [1]}}])
    v3 = call("inspect").get("volume_mm3")
    expect("failed batch rolls back", not r["ok"] and "rolled back" in r.get("error", "") and abs(v3 - v2) < 1e-3,
           f"{v1} {v2} {v3} {r.get('error', '')[:200]}")

    # ---- print package
    r = call("export_capabilities", extension="stl")
    expect("STL translator found", r["ok"] and r.get("available"), json.dumps(r.get("default_options", ""))[:200])
    r = call("export_print_package", folder=os.path.join(work, "pkg"), name="two-bodies")
    files = r.get("files", {})
    expect("print package written", r["ok"] and {"native", "stl", "3mf", "step"} <= set(files), r.get("error", "")[:300])
    expect("mesh has two shells", r.get("mesh", {}).get("shells") == 2, json.dumps(r.get("mesh", {}))[:300])
    expect("3MF readable", r.get("3mf", {}).get("triangles", 0) > 0, json.dumps(r.get("3mf", {}))[:300])
    expect("no temporary folder left", not [x for x in os.listdir(os.path.join(work, "pkg")) if x.startswith(".forge")])
    call("close_document", save=False)

    # ---- parametric profile with an arc, extruded; then a revolve
    call("create_part", name="Profile")
    call("add_parameter", name="L", expression="40 mm")
    call("add_parameter", name="R", expression="10 mm")
    r = call("parametric_profile", plane="XY",
             loops=[[["0", "0"], ["L", "0"], {"arc": ["L", "2 * R"], "center": ["L", "R"]}, ["0", "2 * R"]],
                    {"circle": ["L / 2", "R"], "radius": "3 mm"}], extrude="8 mm", name="Lug")
    expect("profile with arc and hole", r["ok"] and r.get("fully_constrained") and abs(
        (r.get("volume_mm3") or 0) - (40 * 20 + 3.14159265 * 100 / 2 - 3.14159265 * 9) * 8) < 5,
        f"{r.get('volume_mm3')} {r.get('constraint_status')} {r.get('error', '')[:200]}")
    r = call("set_parameter", name="L", expression="50 mm")
    expect("profile follows its parameter", r["ok"] and r.get("volume_change_mm3", 0) > 0)
    r = call("parametric_profile", plane="XZ", loops=[[["20", "0"], ["30", "0"], ["30", "10"], ["20", "10"]]],
             revolve_axis="Z", operation="new_body")
    expect("revolve in one call", r["ok"] and r.get("volume_change_mm3", 0) > 0, r.get("error", "")[:200])

    # ---- split faces: the sketch can't be the tool; fallbacks
    call("create_sketch", plane="XY", offset=8)
    call("draw_line", x1=5, y1=-5, x2=5, y2=30)
    r = call("split_faces", tool="surface")
    expect("split with a hidden surface", r["ok"], r.get("error", "")[:200])
    call("close_document", save=False)
finally:
    r = call("close_private_inventor")
    expect("private Inventor closed", r["ok"], r.get("error", ""))
    F.apartment.close()
print("FAILED:", FAIL if FAIL else "none")
sys.exit(1 if FAIL else 0)
