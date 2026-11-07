"""Scratch debugger: python -X utf8 tests/dbg.py "<python code using s, K, F>" — runs on the active doc."""
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.com import K, items, typed_call, MM  # noqa: E402,F401
from inventor_forge.engine import Forge  # noqa: E402

F = Forge()
s = F.session
code = sys.argv[1] if len(sys.argv) > 1 else open(sys.argv[2]).read()


def run():
    g = {"s": s, "K": K, "items": items, "typed_call": typed_call, "MM": MM, "F": F}
    try:
        exec(code, g)
    except Exception:
        traceback.print_exc()


F.apartment.run(run)
