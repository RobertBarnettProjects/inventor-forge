"""Live: list_references and replace_reference on a small assembly (folder move, a single file, a refused file of a
different design, dry run). Private hidden Inventor only; closed at the end.

    python tests/live_references.py
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

F = Forge(visible=False)
FAIL = []
work = tempfile.mkdtemp(prefix="forge-refs-")
src = os.path.join(work, "parts")
moved = os.path.join(work, "moved")


def call(_tool, **a):
    r = F.safe_call(_tool, a)
    print(f"{_tool:20}", json.dumps(r, default=str)[:500], flush=True)
    return r


def expect(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + f"{name} {info}", flush=True)
    if not cond:
        FAIL.append(name)


def block(name, w, d, h, folder=src):
    call("create_part", name=name)
    call("create_sketch", plane="XY")
    call("draw_rectangle", width=w, height=d)
    call("extrude", distance=h)
    p = os.path.join(folder, name + ".ipt")
    call("save_document", path=p)
    call("close_document", save=False)
    return p


try:
    call("connect", private=True)
    a = block("Base", 100, 60, 10)
    b = block("Post", 10, 10, 40)
    other = block("Other", 20, 20, 20, folder=work)
    call("create_assembly", name="Frame")
    call("place_component", path=a, grounded=True)
    call("place_component", path=b, x=0, y=0, z=10)
    top = os.path.join(work, "Frame.iam")
    call("save_document", path=top)

    r = call("list_references", only_problems=False)
    expect("audit lists both parts as ok", r.get("references", 0) >= 2 and r.get("healthy") is True, r.get("counts"))
    r = call("list_references", root=moved)
    expect("root flags references outside it", r.get("counts", {}).get("outside_root", 0) >= 2, r.get("counts"))

    shutil.copytree(src, moved)
    r = call("replace_reference", old=src + os.sep, new=moved, dry_run=True)
    expect("dry run plans the folder move", r.get("would_replace") == 2, r)
    r = call("replace_reference", old=src + os.sep, new=moved)
    expect("folder move repoints and verifies", r.get("replaced") == 2 and r.get("verified") is True, r)
    expect("backups written", r.get("backed_up", 0) >= 1 and os.path.isdir(r.get("backups", "")))

    r = call("list_references", only_problems=False)
    paths = [row["path"] for row in r.get("rows", [])]
    expect("references now in moved folder", paths and all(os.path.normcase(moved) in os.path.normcase(p) for p in paths),
           paths)

    r = call("replace_reference", old="Post.ipt", new=other)
    expect("a different design is refused by Inventor", r.get("replaced", 0) == 0 and r.get("failures"), r)

    # reopen from disk: the saved files point at the moved folder
    call("close_document", save=False)
    call("open_document", path=top)
    r = call("list_references", only_problems=False)
    paths = [row["path"] for row in r.get("rows", [])]
    expect("repoint survives reopening", paths and all(os.path.normcase(moved) in os.path.normcase(p) for p in paths)
           and r.get("healthy") is True, r.get("counts"))
finally:
    r = call("close_private_inventor")
    expect("private Inventor closed", r.get("ok"), r.get("error", ""))
    F.apartment.close()
print("FAILED:", FAIL if FAIL else "none", "work:", work)
sys.exit(1 if FAIL else 0)
