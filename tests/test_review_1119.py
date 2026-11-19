"""Behaviour fixed after the code review: budgets, deletions, repeated dimensions, table widths, heartbeat ordering."""
import threading
import types

import pytest

from inventor_forge import profile, server
from inventor_forge.com import InventorError
from inventor_forge.registry import load_all
from inventor_forge.tools import drawing


def _meta(name):
    return profile.tool_meta(load_all()[name])


def test_analyze_stress_budget_covers_its_own_solve():
    b = _meta("analyze_stress")["cad/budget"]
    assert profile.budget_for(b, {}) >= 3600 + 1800


def test_empty_fraction_list_counts_the_default_three_solves():
    b = _meta("mesh_convergence")["cad/budget"]
    assert profile.budget_for(b, {"fractions": []}) == profile.budget_for(b, {"fractions": [0.1, 0.07, 0.05]})


def test_deleting_tools_are_marked_and_welds_change_geometry():
    assert _meta("purge_studies")["cad/deletes"] == {"if_args": {"confirm": True}}
    assert _meta("clean_analysis_scratch")["cad/deletes"] == {"if_args": {"confirm": True}}
    assert _meta("weld_body").get("cad/geometry") is True


class _Pt:
    def __init__(self, x, y):
        self.X, self.Y = x / 10, y / 10


class _Dim:
    def __init__(self, value, p, q, text="", ok=True):
        self.ModelValue = value / 10
        self.DimensionLine = types.SimpleNamespace(StartPoint=_Pt(*p), EndPoint=_Pt(*q))
        self.Text = types.SimpleNamespace(FormattedText=text, Text=text)
        self.deleted = False
        self._ok = ok

    def Delete(self):
        if not self._ok:
            raise RuntimeError("refused")
        self.deleted = True


def test_repeats_are_dropped_but_distinct_annotations_kept(monkeypatch):
    monkeypatch.setattr(drawing, "items", lambda c: list(c))
    a = _Dim(200, (85, 95), (185, 95))
    b = _Dim(200, (85, 89), (185, 89))                    # same value, same span, another offset: a repeat
    c = _Dim(200, (85, 83), (185, 83), text="200 ±0.1")  # same span but a tolerance: keep
    d = _Dim(100, (57, 105), (57, 155))                    # vertical
    e = _Dim(100, (51, 105), (51, 155), ok=False)          # a repeat Inventor won't delete: kept, still arranged
    keep, n = drawing._drop_repeats([a, b, c, d, e])
    assert n == 1 and b.deleted and not c.deleted
    assert keep == [a, c, d, e]


def test_table_widths_are_checked_before_inventor_is_touched():
    s = types.SimpleNamespace()                            # no sheet: anything reaching Inventor would fail
    with pytest.raises(InventorError, match="between 2 and 500"):
        drawing.add_custom_table(s, "T", ["A", "B"], [["1", "2"]], column_widths=[20, 0])
    with pytest.raises(InventorError, match="numbers"):
        drawing.add_custom_table(s, "T", ["A"], [["1"]], column_widths=["wide"])


def test_no_progress_after_the_call_has_ended():
    lock = threading.Lock()
    sent = []

    def emit(msg, alive=None):
        with lock:
            if alive is None or alive():
                sent.append(msg)

    s = server.Server.__new__(server.Server)
    s.emit, s.lock = emit, lock
    s.forge = types.SimpleNamespace(session=types.SimpleNamespace(progress=""))
    s._tools_call = lambda name, args: {"content": [], "isError": False}
    s.tools_call("x", {}, token=1)
    assert sent == []                                     # finished before the first beat, and nothing after
