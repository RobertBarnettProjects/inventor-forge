"""Live: the import check and repair_import on an IGES round trip, and the note when the session works on a
document other than the one in front (private Inventor, no mouse).

    python tests/live_import_focus.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

F = Forge(visible=False)
FAIL = []
work = tempfile.mkdtemp(prefix="forge-import-")


def call(tool, **a):
    r = F.safe_call(tool, a)
    print(f"{tool:16}", json.dumps(r, default=str)[:320], flush=True)
    return r


def expect(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + f"{name} {info}", flush=True)
    if not cond:
        FAIL.append(name)


try:
    call("connect", private=True)
    call("create_part", name="Box")
    call("create_sketch", plane="XY")
    call("draw_rectangle", width=40, height=30)
    call("extrude", distance=20)
    igs = os.path.join(work, "box.igs")
    call("export_document", path=igs)
    call("close_document", save=False)
    r = call("open_document", path=igs)
    chk = r.get("import_check")
    expect("open reports the import check", bool(chk), str(chk))
    rep = call("repair_import", fix=True)
    expect("repair_import ran", rep["ok"], rep.get("error", ""))
    after = rep.get("after") or rep.get("before") or {}
    expect("ends with a solid body", after.get("solid", 0) >= 1 and after.get("surface_only", 1) == 0, str(after))
    m = call("mass_properties")
    expect("volume back (24000 mm3)", abs((m.get("volume_mm3") or 0) - 24000) < 1, str(m.get("volume_mm3")))
    # an open surface body: delete the top face without healing, then knit (can't close: 5 faces)
    call("execute_python", code="\n".join([
        "top = max(cdef.SurfaceBodies.Item(1).Faces, key=lambda f: f.PointOnFace.Z)",
        "coll = to.CreateFaceCollection(); coll.Add(top)",
        "cdef.Features.DeleteFaceFeatures.Add(coll, False)"]))
    chk = call("repair_import")
    expect("surface-only body reported", chk.get("before", {}).get("surface_only", 0) >= 1, str(chk.get("before")))
    rep = call("repair_import", fix=True)
    expect("a single open body: open edges found, patching advised", rep["ok"] and rep.get("solid_now") is False
           and rep.get("open_edges") == 4 and "patch" in rep.get("advice", ""),
           str({k: rep.get(k) for k in ("open_edges", "solid_now", "advice", "error")}))
    # document note: act as if attached to the user's Inventor, with another document put in front
    call("create_part", name="Other")
    call("activate_document", name="box")
    F.session.private = False
    F.apartment.run(lambda: F.session.app.Documents.Item(F.session.app.Documents.Count).Activate())
    r = call("set_material", name="Steel, Mild")
    expect("note when another document is in front", "document_note" in r, str(r.get("document_note")))
    F.session.private = True
finally:
    call("close_private_inventor")
print("\nRESULT:", "ALL PASS" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}")
sys.exit(1 if FAIL else 0)
