"""Offline tests for drawing helpers: prompt names, exact component names, the title area for border-only
templates, the Superseded folder, and saving to a document's own path. No Inventor needed.

    python -m pytest tests/test_drawing_helpers.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.com import InventorError  # noqa: E402
from inventor_forge.registry import TOOLS, load_all  # noqa: E402

load_all()
D = sys.modules["inventor_forge.tools.drawing"]
DOCS = sys.modules["inventor_forge.tools.docs"]


def test_prompt_names_include_inventors_attribute_form():
    texts = ["<Prompt ReadOnlyUniqueID='3'>CLIENT</Prompt>", "DRAWN <Prompt>DRAWN BY</Prompt>",
             "<Prompt ReadOnlyUniqueID='9'>CLIENT</Prompt>", "plain"]
    assert D.prompt_names(texts) == ["CLIENT", "DRAWN BY"]


def test_prompt_values_go_as_a_typed_string_array():
    import pythoncom
    v = D.bstr_array(["A", 2])
    assert v.varianttype == pythoncom.VT_ARRAY | pythoncom.VT_BSTR and v.value == ["A", "2"]


class Occ:
    def __init__(self, name):
        self.Name = name


def test_components_are_picked_by_exact_name():
    occs = [Occ("FW_Runner_Deck_Outer:1"), Occ("Runner:1"), Occ("Runner:2"), Occ("Deck:1")]
    assert D.exact_occurrence(occs, "Runner:1").Name == "Runner:1"
    assert D.exact_occurrence(occs, "Deck").Name == "Deck:1"
    with pytest.raises(InventorError, match="several"):
        D.exact_occurrence(occs, "Runner")
    with pytest.raises(InventorError, match="no component"):
        D.exact_occurrence(occs, "Runn")


def test_title_area_stands_in_for_a_missing_title_block():
    class Sheet:
        Name = "Sheet:1"
        TitleBlock = None

        class Parent:
            FullDocumentName = "x.idw"
    D.TITLE_AREAS["default"] = (230.0, 10.0, 410.0, 60.0)
    try:
        rb = D._title_range(Sheet())
        assert rb.MinPoint.X == pytest.approx(23.0) and rb.MaxPoint.Y == pytest.approx(6.0)
        D.TITLE_AREAS[("x.idw", "Sheet:1")] = (0.0, 0.0, 100.0, 20.0)
        assert D._title_range(Sheet()).MaxPoint.X == pytest.approx(10.0)
    finally:
        D.TITLE_AREAS.clear()
        D.TITLE_AREAS["default"] = None
    assert D._title_range(Sheet()) is None


def test_superseded_file_is_moved_not_deleted(tmp_path):
    f = tmp_path / "GA.idw"
    f.write_text("old")
    dest = D.supersede_file(str(f))
    assert not f.exists() and os.path.dirname(dest).endswith("Superseded") and open(dest).read() == "old"


def test_saving_to_own_path_is_a_plain_save():
    assert DOCS.same_file(r"C:\a\b.ipt", r"c:\A\.\b.ipt") and not DOCS.same_file("", r"C:\a.ipt")


def test_section_line_runs_well_past_the_view():
    assert 10 <= D.SECTION_OVERHANG <= 16


def test_new_drawing_tools():
    for n in ("set_title_area", "set_prompted_fields", "set_sheet_format", "set_dimension_precision",
              "supersede_drawing", "apply_positions", "hide_components_in_views"):
        assert n in TOOLS, n
    assert {"list_only", "supersede"} <= set(TOOLS["save_document"].schema["properties"])
