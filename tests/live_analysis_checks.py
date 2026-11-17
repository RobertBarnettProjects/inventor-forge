"""Live: Stress Analysis read-backs on a copy of a model with solved studies: results storage, peak location, and a
second solve of an unchanged study being skipped. Private Inventor; no mouse or keyboard. Closed at the end.

    set INVENTOR_FORGE_STUDY_MODEL=C:\\path\\to\\model.ipt    (a part with at least one solved study)
    python tests/live_analysis_checks.py
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

SRC = os.environ.get("INVENTOR_FORGE_STUDY_MODEL", os.path.expanduser(r"~\Documents\inventor-forge\kart\KartFrame.ipt"))
F = Forge(visible=False)
FAIL = []


def call(_tool, **a):
    r = F.safe_call(_tool, a)
    print(f"{_tool:22}", json.dumps(r, default=str)[:500], flush=True)
    return r


def expect(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + f"{name} {info}", flush=True)
    if not cond:
        FAIL.append(name)


work = tempfile.mkdtemp(prefix="forge-sa-")
model = os.path.join(work, os.path.basename(SRC))
shutil.copy2(SRC, model)
results = os.path.join(os.path.dirname(SRC), os.path.splitext(os.path.basename(SRC))[0])
if os.path.isdir(results):
    shutil.copytree(results, os.path.join(work, os.path.basename(results)))
F.session.workdir = work
try:
    call("connect", private=True)
    call("open_document", path=model)
    st = call("analysis_storage")
    expect("results storage measured", st["ok"] and st.get("result_files", 0) > 0 and st.get("studies", 0) > 0,
           json.dumps(st)[:300])
    studies = [x["name"] for x in call("list_studies").get("studies", []) if x.get("results")]
    expect("a solved study exists", bool(studies), str(studies))
    study = studies[0]
    r = call("read_result_maximum", study=study, locate=True)
    loc = r.get("location", {})
    expect("peak value read", r["ok"] and isinstance(r.get("maximum"), (int, float)), r.get("error", ""))
    expect("peak located on the model", loc.get("found") and loc.get("near_mm"), json.dumps(loc)[:300])
    r1 = call("solve_study", study=study, timeout=900)
    expect("first solve runs", r1["ok"] and not r1.get("skipped"), r1.get("error", ""))
    r2 = call("solve_study", study=study, timeout=900)
    expect("unchanged study not solved again", r2["ok"] and r2.get("skipped"), json.dumps(r2)[:300])
    r = call("purge_studies", keep=[study])
    expect("purge previews without deleting", r["ok"] and "would_delete" in r, json.dumps(r)[:300])
    call("exit_analysis")
    call("close_document", save=False)
finally:
    r = call("close_private_inventor")
    expect("private Inventor closed", r["ok"], r.get("error", ""))
    F.apartment.close()
print("FAILED:", FAIL if FAIL else "none")
sys.exit(1 if FAIL else 0)
