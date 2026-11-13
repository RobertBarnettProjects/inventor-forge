"""Live: orthographic views of a model are projected from its base view, never added as a second base view.
Private Inventor; needs the demo kart (models/kart/out3/GoKart.iam).

    python tests/live_views.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

KART = os.path.join(os.path.dirname(__file__), "..", "..", "models", "kart", "out3", "GoKart.iam")
F = Forge(visible=False)
FAIL = []


def call(tool, **a):
    r = F.safe_call(tool, a)
    print(f"{tool:22}", json.dumps(r, default=str)[:260], flush=True)
    return r


def expect(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + f"{name} {info}", flush=True)
    if not cond:
        FAIL.append(name)


try:
    call("connect", private=True)
    call("set_standard", standard="AS1100")
    r = call("make_assembly_sheet", model=os.path.abspath(KART), sheet_size="auto", drawing_number="SR-100")
    qa = r.get("qa", {})
    expect("GA has FRONT, TOP, RIGHT", r.get("ok"), str(r.get("error", "")))
    expect("GA QA clean", qa.get("total") == 0, str(qa.get("issues")))
    r = call("add_base_view", model=os.path.abspath(KART), x=300, y=100, scale=0.1, orientation="right", name="RIGHT 2")
    expect("second orthographic base view refused", not r["ok"] and "add_projected_view" in r.get("error", ""))
    r = call("add_base_view", model=os.path.abspath(KART), x=700, y=500, scale=0.05, orientation="iso", name="ISO 2")
    expect("extra isometric base view allowed", r["ok"], str(r.get("error", "")))
    call("execute_python", code="\n".join([
        "sh = doc.ActiveSheet",
        "md = sh.DrawingViews.Item(1).ReferencedDocumentDescriptor.ReferencedDocument",
        "v = sh.DrawingViews.AddBaseView(md, tg.CreatePoint2d(30, 10), 0.05, K.kRightViewOrientation, "
        "K.kHiddenLineRemovedDrawingViewStyle)",
        "v.Name = 'SNEAKY'"]))
    qa = call("check_drawing")
    expect("QA flags a second base view made another way",
           any("SNEAKY" in i and "add_projected_view" in i for i in qa.get("issues", [])), str(qa.get("issues")))
finally:
    call("close_private_inventor")
print("\nRESULT:", "ALL PASS" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}")
sys.exit(1 if FAIL else 0)
