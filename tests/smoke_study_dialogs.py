"""Live test, in a private Inventor process, of everything about studies that needs no face picks: creating and
naming studies, committing values into Inventor's value boxes, copying, renaming, deleting. No mouse clicks or typing."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge import uidrive as U  # noqa: E402
from inventor_forge.engine import Forge  # noqa: E402
from inventor_forge.tools import fea  # noqa: E402

F = Forge()
s = F.session


def _no_typing(*_a, **_k):
    raise AssertionError("this test must not fall back to the mouse and keyboard")


fea._type_into = _no_typing
FAIL = []


def call(_tool, **args):
    res = F.safe_call(_tool, args)
    print(f"{_tool:22}", json.dumps(res, ensure_ascii=False)[:500], flush=True)
    if not res["ok"]:
        FAIL.append(_tool)
    return res


def expect(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + f"{name} {info}", flush=True)
    if not cond:
        FAIL.append(name)


def on_com(fn):
    return F.apartment.run(fn)


try:
    call("connect", private=True)
    call("create_part", name="Dialogs")
    call("create_sketch", plane="YZ")
    call("draw_rectangle", width=20, height=10)
    call("extrude", distance=150)
    call("set_material", name="Steel, Mild")
    pid = s.pid

    def build():
        fea._enter_analysis(s)
        fea._create_study(s, pid, study_name="Named study")
        fea._mesh(s, pid, 0.07)
        # the value really was stored: reopen and read it
        fea._run_command(s, "FeaMeshSettingCmd")
        h = fea._dialog(pid, "Mesh Settings")
        shown = U.get_text(U.find(h, cid=10081))
        U.click(U.find(h, cid=2))
        U.wait_gone(h, 10)
        print("mesh box after reopening:", shown)
        expect("mesh value stored", U.same_value(shown, "0.07"), shown)

        # force dialog: values commit before any face is picked
        fea._run_command(s, "FeaCreateLoadForceCmd")
        h = fea._dialog(pid, "Force")
        print(U.dump(h))
        U.set_check(U.find(h, cid=1225), True)
        time.sleep(0.4)
        for cid, v in zip((1216, 1215, 1220), ("12.5", "-30", "400")):
            fea._set_value(h, U.find(h, cid=cid), v, pid)
        shown = [U.get_text(U.find(h, cid=c)) for c in (1216, 1215, 1220)]
        print("force boxes:", shown)
        expect("force values", all(U.same_value(a, b) for a, b in zip(shown, ("12.5", "-30", "400"))), shown)
        # Inventor reformats a value it has parsed ("-30.000 N"); one shown exactly as typed may not be committed
        expect("force values committed (reformatted by Inventor)",
               all(x.strip() != v for x, v in zip(shown, ("12.5", "-30", "400"))), shown)
        U.close(h)
        U.wait_gone(h, 10)

        # modal study with a mode count (the entry that was unreliable when typed)
        fea._create_study(s, pid, modal_modes=3, study_name="Modal three")

    on_com(build)
    r = call("list_studies")
    names = [x["name"] for x in r.get("studies", [])]
    expect("named studies listed", "Named study" in names and "Modal three" in names, names)
    call("activate_study", study="Named study")
    r = call("copy_study", source="Named study", new_name="Copy A")
    expect("copy made", r.get("study") == "Copy A", r)
    r = call("rename_study", study="Copy A", new_name="Copy B")
    names = [x["name"] for x in call("list_studies").get("studies", [])]
    expect("renamed", "Copy B" in names and "Copy A" not in names, names)
    call("delete_study_item", study="Copy B")
    names = [x["name"] for x in call("list_studies").get("studies", [])]
    expect("deleted", "Copy B" not in names, names)
    call("list_analysis_parameters")
    r = F.safe_call("no_such_tool", {})
    expect("unknown tool is reported", not r["ok"])
    # the guard that stops COM calls during a solve
    on_com(lambda: fea._run_command(s, "FeaSimulateCmd"))
    h = U.wait_window(pid, "Simulate", 15)
    r = F.safe_call("status", {})
    expect("calls refused while the Simulate window is open", not r["ok"] and "solve" in r["error"], r.get("error", ""))
    r = F.safe_call("solve_state", {})
    mine = next((x for x in r.get("inventors", []) if x["process"] == r.get("this_session")), {})   # not the user's
    expect("solve_state still answers", r["ok"] and mine.get("solving") == ["Simulate"], r)
    U.close(h)
    U.wait_gone(h, 10)
    time.sleep(1)
finally:
    print("close", F.safe_call("close_private_inventor", {}))
print("\nFAILED:" if FAIL else "\nALL PASSED", FAIL or "")
