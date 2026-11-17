"""Live: components placed into every model state, explicit suppression in a new state, an assembly copy that
repoints a part used only in an inactive state, and drawing helpers (section line overhang, hidden analysis bodies,
title area, Superseded rebuild with hand-placed positions, save preview). Private Inventor only; closed at the end.

    python tests/live_assembly_copy.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

F = Forge(visible=False)
FAIL = []
work = tempfile.mkdtemp(prefix="forge-asm-")
src = os.path.join(work, "K1_skid")


def call(_tool, **a):
    r = F.safe_call(_tool, a)
    print(f"{_tool:22}", json.dumps(r, default=str)[:400], flush=True)
    return r


def expect(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + f"{name} {info}", flush=True)
    if not cond:
        FAIL.append(name)


def block(name, w, d, h):
    call("create_part", name=name)
    call("create_sketch", plane="XY")
    call("draw_rectangle", width=w, height=d)
    call("extrude", distance=h)
    p = os.path.join(src, name + ".ipt")
    call("save_document", path=p)
    call("close_document", save=False)
    return p


try:
    call("connect", private=True)
    a = block("K1_Base", 100, 60, 10)
    b = block("K1_Post", 10, 10, 40)
    c = block("K1_Cap", 30, 30, 5)
    dpart = block("FW_Weld", 5, 5, 5)
    call("create_assembly", name="K1_Skid")
    call("place_component", path=a, grounded=True)
    st = call("add_model_state", name="WithWeld", activate=True)
    states = [x["name"] for x in st.get("states", [])]
    r = call("place_component", path=dpart, x=20, y=0, z=10)
    expect("placed into every model state", r["ok"] and "all 2" in r.get("model_states", ""), r.get("model_states", ""))
    call("place_component", path=b, x=0, y=0, z=10)
    primary = next((n for n in states if n != "WithWeld"), "")
    call("activate_model_state", name=primary)
    r = call("execute_python", code="doc.ComponentDefinition.Occurrences.ItemByName('FW_Weld:1').Suppress()\n"
                                     "doc.ComponentDefinition.Occurrences.ItemByName('FW_Weld:1').Suppressed")
    expect("weld suppressed in the primary state", r.get("result") is True, json.dumps(r)[:200])
    r = call("add_model_state", name="NoPost", activate=False, suppress=["K1_Post:1"])
    expect("new state suppresses what it was told", r["ok"] and r.get("suppressed_in_new_state") == ["K1_Post:1"]
           and r.get("copied_from") == primary, json.dumps(r)[:300])
    r = call("place_component", path=c, x=0, y=0, z=50)
    asm_path = os.path.join(src, "K1_Skid.iam")
    r = call("save_document", path=asm_path, list_only=True)
    expect("save preview lists documents", r["ok"] and r.get("would_save"), json.dumps(r)[:300])
    call("save_document", path=asm_path)

    # ---- copy: the weld part is used only in an inactive state
    dst = os.path.join(work, "K2_skid")
    r = call("copy_assembly", folder=dst, prefix="K2_", old_prefix="K1_", check_contacts=False)
    expect("copy verified", r["ok"] and r.get("verified") is True, json.dumps(r)[:500])
    expect("inactive-state part copied, name case kept", "K2_FW_Weld.ipt" in os.listdir(dst),
           str(os.listdir(dst) if os.path.isdir(dst) else ""))
    expect("all five files copied", r.get("copied") == 5, str(r.get("copied")))
    r = call("referenced_files")
    expect("copy opened and points at copies", r["ok"] and all(dst.lower() in f.lower() for f in r.get("files", [])),
           json.dumps(r.get("files", []))[:400])
    new_asm = os.path.join(dst, "K2_Skid.iam")

    # ---- drawing helpers
    call("create_drawing", sheet_size="A3")
    v = call("add_base_view", model=new_asm, x=150, y=180, scale=1)
    base = v.get("view", {}).get("name", "")
    r = call("add_section_view", parent=base, x=300, y=180, cut="vertical", label="A")
    expect("section view added", r["ok"], r.get("error", ""))
    r = call("execute_python", code="sh = doc.ActiveSheet\nv = sh.DrawingViews.Item(1)\nsk = v.Sketches.Item(v.Sketches.Count)\n"
                                     "ln = sk.SketchLines.Item(1)\np = [sk.SketchToSheetSpace(x.Geometry) for x in "
                                     "(ln.StartSketchPoint, ln.EndSketchPoint)]\n"
                                     "top = v.Top * 10\nbottom = top - v.Height * 10\n"
                                     "[round(min(q.Y for q in p) * 10 - bottom, 2), round(max(q.Y for q in p) * 10 - top, 2)]")
    over = r.get("result") or [0, 0]
    expect("section line runs 12 mm past the view", r["ok"] and abs(over[0] + 12) < 0.5 and abs(over[1] - 12) < 0.5,
           str(over))
    r = call("hide_components_in_views", prefixes=["K1_Post"])
    expect("analysis-only body hidden in views", r["ok"] and r.get("hidden"), json.dumps(r)[:300])
    r = call("set_title_area", x0=250, y0=10, x1=410, y1=50, this_sheet_only=True)
    r = call("add_parts_list", view=base)
    r2 = call("execute_python", code="pl = doc.ActiveSheet.PartsLists.Item(1)\nround(pl.RangeBox.MinPoint.Y * 10, 1)")
    expect("parts list sits above the title area", r2.get("result", 0) >= 50 - 0.5, str(r2.get("result")))

    # ---- Superseded rebuild keeping a note moved by hand
    dwg = os.path.join(dst, "K2_Skid GA.idw")
    call("add_general_notes", text="CHECK WELDS", x=30, y=30)
    call("save_document", path=dwg)
    call("close_document", save=False)
    r = call("supersede_drawing", path=dwg)
    pos = r.get("positions", {})
    expect("old drawing moved to Superseded", r["ok"] and os.path.exists(r.get("moved_to", "")) and
           not os.path.exists(dwg), r.get("error", ""))
    call("create_drawing", sheet_size="A3")
    call("add_general_notes", text="CHECK WELDS", x=200, y=200)
    r = call("apply_positions", positions=pos)
    expect("hand-placed note position restored", r["ok"] and r.get("moved") == 1, json.dumps(r)[:200])
    r = call("save_document", path=dwg)
    expect("rebuild saved to the original name", r["ok"] and os.path.exists(dwg), r.get("error", ""))
    call("close_document", save=False)
finally:
    r = call("close_private_inventor")
    expect("private Inventor closed", r["ok"], r.get("error", ""))
    F.apartment.close()
print("FAILED:", FAIL if FAIL else "none")
sys.exit(1 if FAIL else 0)
