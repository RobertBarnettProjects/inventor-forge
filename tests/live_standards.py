"""Live: a part sheet in every standard, in a private Inventor. Checks the template, the projection angle Inventor
ends up with, the sheet size, and that check_drawing passes. Renders each sheet to PNG in a temp folder.

    python tests/live_standards.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402
from inventor_forge.standards import STANDARDS  # noqa: E402

F = Forge()
FAIL = []
work = tempfile.mkdtemp(prefix="forge-standards-")


def call(tool, **args):
    res = F.safe_call(tool, args)
    print(f"{tool:20}", json.dumps(res, ensure_ascii=False, default=str)[:400], flush=True)
    return res


def expect(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + f"{name} {info}", flush=True)
    if not cond:
        FAIL.append(name)


try:
    expect("connect private", call("connect", private=True)["ok"])
    expect("not chosen yet", call("get_standard").get("chosen") is False)
    call("create_part", name="StdBlock")
    call("create_sketch", plane="XY")
    call("draw_rectangle", width=80, height=50)
    call("extrude", distance=20)
    call("create_sketch", plane="XY", offset=20)
    call("draw_circle", diameter=16)
    call("extrude", distance=20, operation="cut", through_all=True)
    part = os.path.join(work, "StdBlock.ipt")
    expect("save part", call("save_document", path=part)["ok"])
    for k, spec in STANDARDS.items():
        expect(f"{k}: set", call("set_standard", standard=k)["ok"])
        r = call("make_part_sheet", model=part)
        expect(f"{k}: sheet", r["ok"], str(r.get("error", ""))[:200])
        proj = F.apartment.run(lambda: bool(F.session.app.ActiveDocument.StylesManager.ActiveStandardStyle.FirstAngleProjection))
        expect(f"{k}: projection", proj == (spec["projection"] == "first"), f"first_angle={proj}")
        tpl_doc = F.apartment.run(lambda: F.session.app.ActiveDocument.StylesManager.ActiveStandardStyle.Name)
        print(f"     {k}: active standard style {tpl_doc!r}")
        c = call("check_drawing")
        expect(f"{k}: QA clean", c.get("total") == 0, str(c.get("issues", ""))[:300])
        call("render_sheet", path=os.path.join(work, f"sheet-{k}.png"))
        call("close_document", save=False)
    r = call("set_standard", standard="ASME", drawing_units="in")
    r = call("create_drawing", sheet_size="B")
    expect("ASME inch template", r["ok"] and "in" in r.get("template", ""), r.get("template", ""))
finally:
    call("close_private_inventor")
    print("renders in:", work)

print("\nRESULT:", "ALL PASS" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}")
sys.exit(1 if FAIL else 0)
