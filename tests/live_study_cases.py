"""Live retest from the 2026-11-12 review: with a gen_py cache for Inventor in place, open a copy of a model that
has a load study, run two cases with run_study_cases and read the values back from each copy. Private Inventor;
no mouse or keyboard (the copies are made through Inventor's own command, which needs no face picks).

    set INVENTOR_FORGE_STUDY_MODEL=C:\\path\\to\\model.ipt    (a part with at least one solved study with loads)
    python tests/live_study_cases.py [study name]
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.engine import Forge  # noqa: E402

SRC = os.environ.get("INVENTOR_FORGE_STUDY_MODEL", os.path.expanduser(r"~\Documents\inventor-forge\kart\KartFrame.ipt"))
FAIL = []


def expect(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + f"{name} {info}", flush=True)
    if not cond:
        FAIL.append(name)


# the trap the review found: an early-bound cache for Inventor's type library
from win32com.client import gencache  # noqa: E402
try:
    gencache.EnsureModule("{D98A091D-3A0F-4C3E-B36E-61F62068D488}", 0, 1, 0)
    print("gen_py cache for Inventor: present", flush=True)
except Exception as e:  # noqa: BLE001
    print(f"gen_py cache for Inventor: could not build ({e}); the late-binding check still runs", flush=True)

work = tempfile.mkdtemp(prefix="forge-cases-")
model = os.path.join(work, os.path.basename(SRC))
shutil.copy2(SRC, model)
F = Forge()


def call(tool, **args):
    res = F.safe_call(tool, args)
    print(f"{tool:24}", json.dumps(res, ensure_ascii=False, default=str)[:700], flush=True)
    return res


try:
    expect("connect private", call("connect", private=True)["ok"])
    r = call("open_document", path=model)
    expect("open_document", r["ok"])
    st = call("list_studies")
    expect("list_studies works on the opened part (late bound)", st["ok"] and st.get("studies"), str(st.get("error", "")))
    studies = [x["name"] if isinstance(x, dict) else x for x in st.get("studies", [])]
    template = sys.argv[1] if len(sys.argv) > 1 else (studies[0] if studies else "")
    params = call("list_analysis_parameters")
    expect("list_analysis_parameters", params["ok"])
    rows = params.get("parameters") or []
    loads = next((x.get("loads", []) for x in st.get("studies", []) if isinstance(x, dict) and x["name"] == template), [])
    if len(studies) > 1 and loads:            # the first-created study holds the lowest numbers, 3 (X, Y, Z) per force
        rows = rows[:3 * len(loads)]
    print("template parameters:", [(p.get("name"), p.get("expression")) for p in rows])
    if not rows:
        raise SystemExit("the template study has no load parameters to vary")

    def scaled(k):
        out = []
        for p in rows:
            ex = str(p.get("expression", ""))
            num, _, unit = ex.partition(" ")
            try:
                out.append(f"{float(num) * k:g} {unit}".strip())
            except ValueError:
                out.append(None)
        return out

    cases = [{"name": "Retest x0.5", "values": scaled(0.5)}, {"name": "Retest x2", "values": scaled(2.0)}]
    res = call("run_study_cases", template=template, cases=cases, results_path=os.path.join(work, "cases.json"),
               timeout=1800)
    expect("run_study_cases", res["ok"], str(res.get("error", ""))[:300])
    got = res.get("cases") or {}
    rows_out = [got.get(c["name"], {}) for c in cases]
    for case, row in zip(cases, rows_out):
        expect(f"{case['name']}: done", row.get("status") == "done", str(row)[:300])
        written = row.get("parameters_written") or []
        expect(f"{case['name']}: values written and read back",
               len(written) == len([v for v in case["values"] if v is not None]), str(written)[:300])
        expect(f"{case['name']}: no duplicate copies", not row.get("duplicate_copies"), str(row.get("duplicate_copies")))
    peaks = [row.get("results", {}) for row in rows_out]
    print("peaks:", json.dumps(peaks, default=str)[:600])
finally:
    call("close_private_inventor")
    print("work folder:", work)

print("\nRESULT:", "ALL PASS" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}")
sys.exit(1 if FAIL else 0)
