"""Offline tests for the fixes from the 2026-11-12 review: study-copy parameter mapping, the COM wait budget,
late binding that survives a gen_py cache, and the mouse readiness check. No Inventor needed.

    python -m pytest tests/test_review_fixes.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.com import InventorError  # noqa: E402
from inventor_forge.registry import load_all  # noqa: E402

TOOLS = load_all()
studies = sys.modules["inventor_forge.tools.studies"]


def sa(*values, start=1):
    return [(f"sa_{start + i}", v) for i, v in enumerate(values)]


# --------------------------------------------------------------------------- item 1: copy parameter mapping
def test_copy_found_by_value_although_inventor_renumbers_everything():
    # another study (A, B), then the template (T1..T3); after the copy every name has moved
    before = sa("1 N", "2 N", "0 N", "-30 N", "400 N")
    after = sa("1.000 N", "2.000 N", "0.000 N", "-30.000 N", "400.000 N", "0.000 N", "-30.000 N", "400.000 N", start=11)
    assert studies._inserted(before, after) == ["sa_16", "sa_17", "sa_18"]


def test_template_keeps_the_lowest_numbered_set_when_the_copy_lands_first():
    before = sa("5 N", "0 N", "-30 N")
    after = sa("5 N", "0 N", "-30 N", "0 N", "-30 N")
    # values can't tell the template from the copy; the lowest-numbered set stays the template's
    assert studies._inserted(before, after) == ["sa_4", "sa_5"]


def test_transient_second_set_is_returned_so_both_get_written():
    before = sa("0 N", "-30 N")
    after = sa("0 N", "-30 N", "0 N", "-30 N", "0 N", "-30 N")
    new = studies._inserted(before, after)
    assert studies._sets(new, 2, "case") == [["sa_3", "sa_4"], ["sa_5", "sa_6"]]


def test_unmatched_parameters_stop_before_anything_is_written():
    before = sa("0 N", "-30 N")
    after = sa("7 N", "8 N", "9 N")
    with pytest.raises(InventorError, match="matched by value"):
        studies._inserted(before, after)


def test_sets_must_divide_evenly():
    with pytest.raises(InventorError, match="whole number of sets"):
        studies._sets(["sa_3", "sa_4", "sa_5"], 2, "case")


def test_set_with_a_numbering_gap_is_refused():
    with pytest.raises(InventorError, match="numbered run"):
        studies._sets(["sa_3", "sa_7"], 2, "case")


def test_copy_waits_long_enough_for_large_studies():
    assert studies.COPY_WAIT >= 40


# --------------------------------------------------------------------------- item 4: COM wait vs the tool's timeout
def test_wait_covers_a_long_solve():
    from inventor_forge.engine import call_budget
    assert call_budget(TOOLS["solve_study"].fn, {}) > 3600
    assert call_budget(TOOLS["solve_study"].fn, {"timeout": 7200}) > 7200


def test_wait_covers_every_case_of_a_batch():
    from inventor_forge.engine import call_budget
    cases = [{"name": str(i), "values": []} for i in range(4)]
    assert call_budget(TOOLS["run_study_cases"].fn, {"template": "S", "cases": cases}) > 4 * 3600
    assert call_budget(TOOLS["mesh_convergence"].fn, {"study": "S"}) > 3 * 3600


def test_tools_without_a_timeout_keep_the_default():
    from inventor_forge.engine import DEFAULT_WAIT, call_budget
    assert call_budget(TOOLS["status"].fn, {}) == DEFAULT_WAIT


# --------------------------------------------------------------------------- item 3: early binding
@pytest.mark.skipif(sys.platform != "win32", reason="COM")
def test_method_results_stay_late_bound_with_a_gen_py_cache():
    import pythoncom
    import win32com.client.dynamic as dyn
    from win32com.client import gencache
    pythoncom.CoInitialize()                 # another test's apartment may have left this thread uninitialised

    from inventor_forge.com import _late_class, late
    gencache.EnsureModule("{420B2830-E718-11CF-893D-00A0C9054228}", 0, 1, 0)   # Scripting, cached like Inventor was
    plain = dyn.Dispatch("Scripting.FileSystemObject").GetFolder("C:\\")
    assert "gen_py" in type(plain).__module__          # the trap: a "late-bound" method result came back early-bound
    fso = late(dyn.Dispatch("Scripting.FileSystemObject"))
    folder = fso.GetFolder("C:\\")
    assert isinstance(folder, _late_class())
    assert isinstance(folder.Drive, _late_class())     # properties too
    assert isinstance(late(plain), _late_class()) and late(plain).Path == "C:\\"
    assert late(None) is None and late(5) == 5


# --------------------------------------------------------------------------- item 7: elevated windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_mouse_ready_answers_with_a_reason():
    from inventor_forge import uidrive as U
    ok, why = U.mouse_ready()
    assert isinstance(ok, bool) and (ok or why)
    assert U.elevated(os.getpid()) in (True, False, None)


# --------------------------------------------------------------------------- item 8: degenerate elements
def test_degenerate_element_is_treated_as_a_failed_solve():
    fea = sys.modules["inventor_forge.tools.fea"]
    assert any(k in "Degenerate element found (S020)".lower() for k in fea.FATAL_SOLVE)


# --------------------------------------------------------------------------- standards chosen per session
def test_standards_resolve_and_follow_the_session():
    from inventor_forge.session import Session
    from inventor_forge.standards import STANDARDS, StandardError, key, third_angle
    assert key("AS 1100") == "AS1100" and key("ansi") == "ASME" and key("bs 8888") == "BS8888"
    assert third_angle("ASME") and third_angle("JIS") and not third_angle("ISO") and not third_angle("DIN")
    with pytest.raises(StandardError):
        key("klingon")
    s = Session()
    assert s.standard_key() == "AS1100"
    TOOLS["set_standard"].fn(s, "DIN")
    assert s.standard_key() == "DIN" and s.standard_key("ASME") == "ASME"
    assert TOOLS["get_standard"].fn(s)["projection"] == "first-angle"
    assert len(TOOLS["list_standards"].fn(s)["standards"]) == len(STANDARDS)
    with pytest.raises(InventorError):
        TOOLS["set_standard"].fn(s, "ISO", drawing_units="in")


def test_copy_between_existing_parameters_is_refused():
    # A=[0, 1000, 0], B=[0, 500, 0]; the copy of A lands between them: values can't say whose is whose
    before = sa("0 N", "1000 N", "0 N", "0 N", "500 N", "0 N")
    after = sa("0 N", "1000 N", "0 N", "0 N", "1000 N", "0 N", "0 N", "500 N", "0 N")
    with pytest.raises(InventorError, match="told apart"):
        studies._inserted(before, after)


def test_near_equal_values_are_not_the_same_parameter():
    before = sa("100 N", "100.05 N")
    after = sa("100 N", "100 N", "100.05 N")
    with pytest.raises(InventorError):
        studies._inserted(before, after)


def test_names_that_become_file_names_are_plain():
    from inventor_forge.com import plain_name
    assert plain_name(r"C:\Users\Public\x") == "x"
    assert plain_name(r"..\..\x") == "x" and plain_name("a/b/../c") == "c" and plain_name("") == "untitled"


def test_standard_labels_are_accepted():
    from inventor_forge.standards import key
    assert key("ASME Y14.5") == "ASME" and key("JIS B 0001") == "JIS" and key("DIN EN ISO 128") == "DIN"
    assert key("ISO 128") == "ISO" and key("AS 1100.101") == "AS1100"


# --------------------------------------------------------------------------- MCP survey adoptions
def test_destructive_and_read_only(monkeypatch):
    from inventor_forge.engine import Forge, tool_enabled
    from inventor_forge.registry import DESTRUCTIVE
    from inventor_forge.server import Server
    assert {"execute_python", "close_document", "answer_dialog"} <= DESTRUCTIVE
    rows = {t["name"]: t["annotations"] for t in Server.__new__(Server).__class__.tools_list(
        type("S", (), {"forge": type("F", (), {"tools": TOOLS})()})())}
    assert rows["execute_python"]["destructiveHint"] and not rows["list_faces"]["destructiveHint"]
    monkeypatch.setenv("INVENTOR_FORGE_READ_ONLY", "1")
    f = Forge.__new__(Forge)
    f.tools = TOOLS
    with pytest.raises(InventorError, match="read-only"):
        f.call("extrude", {"distance": 5})
    monkeypatch.setenv("INVENTOR_FORGE_TOOLSETS", "sketch")
    assert tool_enabled(TOOLS["draw_line"]) and not tool_enabled(TOOLS["extrude"]) and tool_enabled(TOOLS["pending_call"])


def test_new_tools_registered():
    for n in ("check_sketch", "pending_call", "answer_dialog"):
        assert n in TOOLS
    assert "undo_on_error" in TOOLS["execute_python"].schema["properties"]
    assert "views" in TOOLS["screenshot"].schema["properties"]


def test_call_held_by_a_dialog_comes_back_early(monkeypatch):
    """The engine reports an Inventor dialog that holds a call, then pending_call follows it to the end."""
    import threading

    from inventor_forge import engine as E
    from inventor_forge import uidrive as U
    from inventor_forge.com import Apartment
    release = threading.Event()
    f = E.Forge.__new__(E.Forge)
    f.tools, f.pending, f.apartment = TOOLS, None, Apartment("test-sta")
    f._pending_lock = threading.Lock()
    f.failures = E.FailureMemory()
    f.session = type("S", (), {"pid": 4242, "solver_busy": lambda self: [], "forge": None})()
    f.session.forge = f
    dialog = [{"hwnd": 7, "title": "Inventor", "text": "Sketch not closed", "buttons": ["OK"]}]
    shown = {"on": False}
    monkeypatch.setattr(U, "dialog_rows", lambda pid, skip=None: dialog if shown["on"] else [])
    monkeypatch.setattr(U, "modal_blocked", lambda pid: shown["on"])
    monkeypatch.setattr(E, "DIALOG_GRACE", 0.5)
    real = TOOLS["status"]

    def held(s):
        shown["on"] = True
        release.wait(10)
        shown["on"] = False
        return {"done": True}
    monkeypatch.setitem(TOOLS, "status", E.Tool("status", "session", held, "", {"type": "object", "properties": {}},
                                                  False, True) if hasattr(E, "Tool") else
                        type(real)("status", "session", held, "", {"type": "object", "properties": {}}, False, True))
    with pytest.raises(InventorError, match="Sketch not closed"):
        f.call("status")
    p = TOOLS["pending_call"].fn(f.session)
    assert p["pending"] and p["dialogs"][0]["text"] == "Sketch not closed"
    with pytest.raises(InventorError, match="no tool call is waiting"):     # bound to the held call: the user's own
        TOOLS["answer_dialog"].fn(type("S", (), {"pid": 1, "forge": None})(), button="OK")
    with pytest.raises(InventorError, match="still waiting"):
        f.call("status")
    release.set()
    p = TOOLS["pending_call"].fn(f.session, wait_seconds=5)
    assert p["finished"] and p["result"] == {"done": True} and f.pending is None
    f.apartment.close()


def test_library_and_install_folders_are_protected(tmp_path, monkeypatch):
    docs = sys.modules["inventor_forge.tools.docs"]
    with pytest.raises(InventorError, match="Autodesk"):
        docs._guard_write(r"C:\Users\Public\Documents\Autodesk\Inventor 2027\Templates\en-US\Metric\Standard.ipt")
    with pytest.raises(InventorError, match="Autodesk"):
        docs._guard_write(os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Autodesk", "x.ipt"))
    mine = tmp_path / "keep"
    mine.mkdir()
    monkeypatch.setenv("INVENTOR_FORGE_PROTECTED", str(mine))
    with pytest.raises(InventorError, match="INVENTOR_FORGE_PROTECTED"):
        docs._guard_write(str(mine / "a.ipt"))
    ro = tmp_path / "ro.ipt"
    ro.write_text("x")
    os.chmod(ro, 0o444)
    with pytest.raises(InventorError, match="read-only"):
        docs._guard_write(str(ro))
    docs._guard_write(str(tmp_path / "fine.ipt"))


def test_case_failures_are_told_apart_from_inventor_failures():
    st = sys.modules["inventor_forge.tools.studies"]
    assert st._case_level(InventorError("solve failed: degenerate element found"))
    assert not st._case_level(InventorError("The RPC server is unavailable"))
    assert not st._case_level(RuntimeError("boom"))


def test_file_arguments_are_declared_and_exist():
    from inventor_forge.fileargs import NAMES, READS, WRITES
    for table in (WRITES, READS, NAMES):
        for tool_name, keys in table.items():
            assert tool_name in TOOLS, tool_name
            for k in keys:
                assert k in TOOLS[tool_name].schema["properties"], (tool_name, k)
    import re
    # every argument whose name says file/path is declared one way or the other
    for n, t in TOOLS.items():
        for k in t.schema["properties"]:
            if re.search(r"(^|_)(path|file|folder|dir)$", k):
                assert k in WRITES.get(n, ()) + READS.get(n, ()), (n, k)


def test_rejected_operations_come_with_a_next_step():
    from inventor_forge.hints import hint_for
    assert "list_edges" in hint_for("fillet", "Exception occurred")
    assert "check_sketch" in hint_for("extrude", "no closed profile")
    assert "direction" in hint_for("extrude", "Exception occurred")
    assert "pending_call" in hint_for("create_part", "call was rejected by callee (busy)")
    assert hint_for("list_faces", "Exception occurred") == ""


def test_every_declared_write_goes_through_the_gate():
    import inspect
    from inventor_forge.fileargs import WRITES
    for name in WRITES:
        src = inspect.getsource(TOOLS[name].fn)
        assert "output_path(" in src or "_guard_write(" in src or "save_document(" in src, name


def test_read_only_mode_blocks_writes_even_from_reading_tools(monkeypatch, tmp_path):
    from inventor_forge.writes import output_path
    monkeypatch.setenv("INVENTOR_FORGE_READ_ONLY", "1")
    with pytest.raises(InventorError, match="read-only"):
        output_path(str(tmp_path), "bom.csv", "exports", ".csv")


def test_protected_folder_list_tolerates_spaces(monkeypatch, tmp_path):
    from inventor_forge.writes import guard
    monkeypatch.setenv("INVENTOR_FORGE_PROTECTED", f"  {tmp_path}  ;")
    with pytest.raises(InventorError):
        guard(str(tmp_path / "x.ipt"))


def test_unlimited_wait_is_allowed():
    from inventor_forge.engine import call_budget
    assert call_budget(TOOLS["status"].fn, {}, None) is None
