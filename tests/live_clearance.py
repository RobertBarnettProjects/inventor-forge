"""Live: sweep_clearance on two blocks, and the hint on a rejected fillet (private Inventor, no mouse).

    python tests/live_clearance.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

F = Forge(visible=False)
FAIL = []
work = tempfile.mkdtemp(prefix="forge-clear-")


def call(tool, **a):
    r = F.safe_call(tool, a)
    print(f"{tool:18}", json.dumps(r, default=str)[:260], flush=True)
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
    p = os.path.join(work, name + ".ipt")
    call("save_document", path=p)
    return p


try:
    call("connect", private=True)
    a = block("Base", 60, 60, 10)
    edges = call("list_edges").get("edges", [])
    r = call("shell", thickness=30)
    expect("rejected shell comes with a next step", not r["ok"] and "Try:" in r.get("error", ""), r.get("error", "")[:200])
    call("close_document", save=False)
    b = block("Slider", 20, 20, 20)
    call("close_document", save=False)
    call("create_assembly", name="Rig")
    call("place_component", path=a, grounded=True)
    call("place_component", path=b, x=0, y=0, z=40)
    top = call("inspect_assembly", faces_of="Base:1")
    up = next(f["index"] for f in top["faces"] if f.get("normal") == [0, 0, 1] or f.get("normal") == [0.0, 0.0, 1.0])
    bot = call("inspect_assembly", faces_of="Slider:1")
    down = next(f["index"] for f in bot["faces"] if f.get("normal") in ([0, 0, -1], [0.0, 0.0, -1.0]))
    c = call("add_constraint", type="mate", occurrence_one="Base:1", entity_one=f"face:{up}",
             occurrence_two="Slider:1", entity_two=f"face:{down}", offset=20)
    s = call("sweep_clearance", constraint=c["constraint"], start=20, stop=-5, steps=5, moving="Slider:1")
    expect("sweep ran", s["ok"], s.get("error", ""))
    expect("clash found once the gap closes", s.get("first_clash_at") is not None and s["first_clash_at"] < 0,
           str(s.get("first_clash_at")))
    expect("tightest clearance reported", s.get("tightest_clearance") and s["tightest_clearance"]["gap_mm"] <= 5.01,
           str(s.get("tightest_clearance")))
    g = [x["min_gap_mm"] for x in s.get("steps", [])][:3]
    expect("gaps follow the offset", g and abs(g[0] - 20) < 0.05, str(g))
    after = call("inspect_assembly")
    expect("constraint put back", s.get("restored", "").startswith("20"), s.get("restored"))
finally:
    call("close_private_inventor")
print("\nRESULT:", "ALL PASS" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}")
sys.exit(1 if FAIL else 0)
