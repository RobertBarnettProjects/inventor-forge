"""Live: screenshot(up="z") shows a Z-up part the way it sits on a print bed. Private Inventor; no models needed.

    python tests/live_z_up_views.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

F = Forge(visible=False)
FAIL = []
OUT = os.path.join(tempfile.gettempdir(), "forge-z-up")
os.makedirs(OUT, exist_ok=True)


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
    call("create_part", name="ZUpTray")
    # a 60 x 40 footprint on XY, 15 mm tall in Z, with a pocket opening upward (+Z)
    call("create_sketch", plane="XY")
    call("draw_rectangle", width=60, height=40)
    call("extrude", distance=15)
    call("create_sketch", plane="XY", offset=15)
    call("draw_rectangle", width=50, height=30)
    call("extrude", distance=10, operation="cut")
    r = call("screenshot", path=OUT + os.sep, views="iso,top,front", up="z")
    imgs = r.get("images", []) if r.get("ok", True) else []
    expect("three Z-up views", len(imgs) == 3, str(r.get("error", "")))
    top = next((i for i in imgs if i["view"] == "top"), {})
    front = next((i for i in imgs if i["view"] == "front"), {})
    # top looks down Z: the 60 x 40 footprint fills it; front looks along Y: 60 x 15. Both are fitted, so the
    # image aspect tells them apart through mm_per_px (larger for top, which shows more)
    expect("top and front differ in scale", top.get("mm_per_px") and front.get("mm_per_px")
           and top["mm_per_px"] != front["mm_per_px"], f"{top.get('mm_per_px')} {front.get('mm_per_px')}")
    r = call("screenshot", path=os.path.join(OUT, "bad.png"), view="home", up="z")
    expect("unknown Z-up view refused", "error" in r and "up='z'" in r["error"])
    print("images in", OUT)
finally:
    call("close_private_inventor")
print("FAILURES:", FAIL or "none")
