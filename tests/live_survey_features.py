"""Live: features adopted from the MCP survey (private Inventor, no mouse).

    python tests/live_survey_features.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

F = Forge(visible=True)
FAIL = []
work = tempfile.mkdtemp(prefix="forge-survey-")
F.session.workdir = work


def call(tool, **a):
    r = F.safe_call(tool, a)
    print(f"{tool:18}", json.dumps(r, default=str)[:300], flush=True)
    return r


def expect(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + f"{name} {info}", flush=True)
    if not cond:
        FAIL.append(name)


try:
    call("connect", private=True)
    call("create_part", name="Gap")
    call("create_sketch", plane="XY")
    for x1, y1, x2, y2 in ((0, 0, 40, 0), (40, 0, 40, 30), (40, 30, 0, 30), (0, 30, 0, 0.6)):
        call("draw_line", x1=x1, y1=y1, x2=x2, y2=y2)
    r = call("extrude", distance=10)
    expect("extrude error names the gap", not r["ok"] and "gap" in r.get("error", "") and "0.6" in r.get("error", ""),
           r.get("error", "")[:200])
    c = call("check_sketch")
    expect("check_sketch finds the gap", c.get("gaps") and abs(c["gaps"][0]["gap_mm"] - 0.6) < 1e-3)
    call("draw_line", x1=0, y1=0.6, x2=0, y2=0)
    r = call("extrude", distance=10)
    expect("closed after the fix", r["ok"], r.get("error", ""))
    n_before = len(call("list_features").get("features", []))
    r = call("execute_python", code="cdef.Features.ExtrudeFeatures.AddByDistanceExtent(cdef.Sketches.Item(1).Profiles.AddForSolid(), 1.0, K.kPositiveExtentDirection, K.kJoinOperation)\nraise RuntimeError('boom')")
    n_after = len(call("list_features").get("features", []))
    expect("failed snippet rolled back", r.get("ok_python") is False and r.get("rolled_back") and n_after == n_before,
           f"{n_before} -> {n_after}")
    expect("snippet logged", os.path.exists(os.path.join(work, "execute_python.log")))
    r = call("screenshot", views="iso,front,top", path=os.path.join(work, "shot"))
    imgs = r.get("images", [])
    expect("three views in one call with scale", len(imgs) == 3 and all(i.get("mm_per_px") for i in imgs) and
           all(os.path.exists(i["path"]) for i in imgs))
    # Inventor's Open prompt (WPF) shown asynchronously; answer_dialog closes it with a window message
    call("execute_python", undo_on_error=False,
         code="app.CommandManager.ControlDefinitions.Item('AppFileOpenCmd').Execute2(False)")
    import time
    from inventor_forge import uidrive as U
    time.sleep(3)
    rows = U.dialog_rows(F.session.pid)
    expect("Open prompt listed while Inventor is blocked", any(r_["title"] == "Open" for r_ in rows) and U.modal_blocked(F.session.pid))
    r0 = call("answer_dialog", button="Cancel", title="Open")
    expect("a dialog no call waits on is left alone by default", not r0["ok"])
    a = call("answer_dialog", button="Cancel", title="Open", any_dialog=True)
    expect("answered with a window message", a["ok"], a.get("error", ""))
    time.sleep(2)
    expect("prompt gone", not U.modal_blocked(F.session.pid))
    expect("server usable again", call("status")["ok"])
finally:
    call("close_private_inventor")
print("\nRESULT:", "ALL PASS" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}")
sys.exit(1 if FAIL else 0)
