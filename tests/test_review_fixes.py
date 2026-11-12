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
