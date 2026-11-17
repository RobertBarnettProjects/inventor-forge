"""Offline tests for modelling and assembly helpers: copy planning, range-box diffs, renames read back, model-state
member scope. No Inventor needed.

    python -m pytest tests/test_modelling.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.com import InventorError  # noqa: E402
from inventor_forge.registry import TOOLS, load_all  # noqa: E402

load_all()
A = sys.modules["inventor_forge.tools.assembly"]
I = sys.modules["inventor_forge.tools.inspect"]


def test_copy_renames_file_names_only():
    assert A.renamed("SK1_Base.ipt", "SK2_", "SK1_") == "SK2_Base.ipt"
    assert A.renamed("Base.ipt", "SK2_") == "SK2_Base.ipt"
    root = r"C:\jobs\SK1_skid"
    plan = A.copy_plan([r"C:\jobs\SK1_skid\SK1_frame.iam", r"C:\jobs\SK1_skid\SK1_parts\SK1_plate.ipt",
                        r"C:\Library\bolt.ipt"], root, r"D:\out\SK2_skid", "SK2_", "SK1_")
    vals = sorted(plan.values())
    assert vals == [r"D:\out\SK2_skid\SK1_parts\SK2_plate.ipt", r"D:\out\SK2_skid\SK2_frame.iam"]
    # the sub-folder keeps its name even though it starts with the old prefix; library files aren't copied
    assert not any("bolt" in v for v in vals)


def test_range_box_diff_reports_what_moved_and_resized():
    before = {"Deck:1": (0, 0, 0, 100, 50, 10), "Lug:1": (90, 0, 10, 100, 10, 30), "Pin:1": (0, 0, 0, 1, 1, 1)}
    after = {"Deck:1": (0, 0, 0, 120, 50, 10), "Lug:1": (110, 0, 10, 120, 10, 30), "Pin:1": (0, 0, 0, 1, 1, 1),
             "New:1": (0, 0, 0, 2, 2, 2)}
    rows = {r["name"]: r for r in I.box_changes(before, after)}
    assert rows["Deck:1"]["change"] == "resized" and rows["Deck:1"]["size_change_mm"][0] == 20
    assert rows["Lug:1"]["change"] == "moved" and rows["Lug:1"]["centre_shift_mm"] == [20, 0, 0]
    assert "Pin:1" not in rows and rows["New:1"]["change"] == "appeared"
    assert I.box_changes(after, before)[-1]["change"] == "gone"


def test_rename_is_read_back():
    from inventor_forge.session import set_name

    class Ignores:
        Name = "Extrusion1"

        def __setattr__(self, k, v):
            pass                              # Inventor keeps the old name without an error

    class Takes:
        Name = "Extrusion1"
    with pytest.raises(InventorError, match="kept the name"):
        set_name(Ignores(), "Plate")
    t = Takes()
    assert set_name(t, "Plate") == "Plate"


def test_components_go_into_every_model_state():
    class States:
        Count = 3
        MemberEditScope = 57601
    class CD:
        ModelStates = States()
    class Doc:
        ComponentDefinition = CD()
    doc = Doc()
    from inventor_forge.com import K
    with A.all_members(doc) as n:
        assert n == 3 and doc.ComponentDefinition.ModelStates.MemberEditScope == K.get("kEditAllMembers", 57602)
    assert doc.ComponentDefinition.ModelStates.MemberEditScope == 57601


def test_new_modelling_tools_and_switches():
    for n in ("copy_assembly", "set_display", "rename"):
        assert n in TOOLS, n
    assert "tool" in TOOLS["split_faces"].schema["properties"]
    assert {"suppress", "unsuppress"} <= set(TOOLS["add_model_state"].schema["properties"])
