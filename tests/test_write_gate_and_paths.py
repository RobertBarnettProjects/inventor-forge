"""Offline tests: whose solver processes may be ended, writes that skipped the
write gate, relative paths, the part template choice and malformed MCP messages. Inventor is replaced by fakes."""
import os
from types import SimpleNamespace

import pytest

from inventor_forge import writes
from inventor_forge.com import InventorError
from inventor_forge.stall import orphaned
from inventor_forge.tools import assembly, docs, drawing, printing, studies


@pytest.fixture
def scope(tmp_path, monkeypatch):
    """A call whose scope is the job folder alone (forge's own temp folder pointed away from pytest's)."""
    monkeypatch.setattr(writes.tempfile, "gettempdir", lambda: str(tmp_path / "forge-temp"))
    job = tmp_path / "job"
    job.mkdir()
    mark = writes.use_scope({"dirs": [str(job)], "files": []})
    yield job
    writes.reset_scope(mark)


# ------------------------------------------------------------------ whose solver processes are orphans
def test_a_solver_under_a_running_inventor_is_never_an_orphan():
    parents = {20: 10, 31: 30, 30: 10, 40: 99, 51: 50, 50: 98}
    # 20: started by Inventor 10; 31: started through another process (30) by Inventor 10: both are in use
    # 40: its Inventor (99) has gone; 51: started through a process whose Inventor (98) has gone
    assert orphaned([20, 31, 40, 51], {10}, parents) == [40, 51]


def test_orphan_search_survives_a_loop_in_the_process_table():
    assert orphaned([5], {1}, {5: 6, 6: 5}) == [5]          # reused process ids can point at each other
    assert orphaned([5], {1}, {}) == [5]


# ------------------------------------------------------------------ copies and backups never overwrite each other
def test_two_sources_copied_to_one_name_are_reported():
    files = [r"C:\job\A_plate.ipt", r"C:\job\plate.ipt", r"C:\job\top.iam"]
    plan = assembly.copy_plan(files, r"C:\job", r"C:\new", "B_", "A_")
    assert assembly.plan_clashes(plan) == [os.path.abspath(r"C:\new\B_plate.ipt")]
    assert assembly.plan_clashes(assembly.copy_plan(files, r"C:\job", r"C:\new", "B_")) == []


def test_backups_of_same_named_files_get_their_own_names():
    names = assembly.backup_names([r"C:\job\a\Plate.ipt", r"C:\job\b\plate.ipt", r"C:\job\top.iam"])
    assert list(names.values()) == ["Plate.ipt", "plate (2).ipt", "top.iam"]


# ------------------------------------------------------------------ relative paths of files that are read
def test_a_relative_read_path_is_found_under_the_workdir(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    (work / "bracket.ipt").write_text("x")
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    (elsewhere / "only_here.ipt").write_text("x")
    monkeypatch.chdir(elsewhere)
    assert writes.input_path(str(work), "bracket.ipt") == str(work / "bracket.ipt")
    assert writes.input_path(str(work), "only_here.ipt") == str(elsewhere / "only_here.ipt")
    assert writes.input_path(str(work), "missing.ipt") == str(work / "missing.ipt")     # named under the workdir
    assert writes.input_path(str(work), str(tmp_path / "abs.ipt")) == str(tmp_path / "abs.ipt")


# ------------------------------------------------------------------ writes that skipped the gate
def test_superseding_checks_the_folder_the_file_moves_into(scope, tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    f = outside / "old.idw"
    f.write_text("x")
    with pytest.raises(writes.NeedsApproval) as e:
        drawing.supersede_file(str(f))
    assert str(outside / "Superseded") in str(e.value)
    assert f.exists() and not (outside / "Superseded").exists()         # nothing moved, nothing made
    mark = writes.use_scope({"dirs": [str(scope)], "files": [str(outside / "Superseded")]})      # approved: the folder
    try:
        dest = drawing.supersede_file(str(f))
    finally:
        writes.reset_scope(mark)
    assert os.path.dirname(dest) == str(outside / "Superseded") and not f.exists()


def test_a_result_picture_goes_through_the_gate(scope, tmp_path):
    s = SimpleNamespace(workdir=str(tmp_path / "not-the-job"), view=lambda: pytest.fail("rendered before the check"))
    with pytest.raises(writes.NeedsApproval):
        studies._picture(s, "Study 1", "Von Mises Stress", "iso")
    assert not (tmp_path / "not-the-job").exists()


def test_a_refused_print_package_makes_no_folder(scope, tmp_path):
    d = SimpleNamespace(DisplayName="bracket.ipt")
    s = SimpleNamespace(doc=lambda: d, kind=lambda _d: "part", workdir=str(scope))
    target = tmp_path / "usb" / "print"
    with pytest.raises(writes.NeedsApproval) as e:
        printing.export_print_package(s, folder=str(target), formats="stl,step")
    named = str(e.value)
    assert str(target / "bracket.stl") in named and str(target / "bracket.step") in named     # all in one refusal
    assert not target.exists()


# ------------------------------------------------------------------ the test hook never quits a user's Inventor
def test_the_exit_hook_leaves_an_attached_inventor_alone(monkeypatch):
    def quit_():
        raise AssertionError("quit an Inventor this session only attached to")
    s = SimpleNamespace(private=False, app=SimpleNamespace(Quit=quit_, SilentOperation=False))
    monkeypatch.setenv("INVENTOR_FORGE_TEST_EXIT_AT", "case 1")
    monkeypatch.setattr(studies, "_study_nodes", lambda _s: {"case 1": object()})
    with pytest.raises(InventorError, match="already exists"):         # carried on to the ordinary checks instead
        studies._run_case(s, 1, "Template", {"name": "case 1"}, [], 10.0, {"cases": {}}, "")


# ------------------------------------------------------------------ the stock part template is used
def test_a_plain_part_starts_from_the_stock_template(monkeypatch):
    used = []
    d = SimpleNamespace(SubType="", DisplayName="", Activate=lambda: None)
    app = SimpleNamespace(FileManager=SimpleNamespace(GetTemplateFile=lambda *a: "PROJECT TEMPLATE"),
                          Documents=SimpleNamespace(Add=lambda kind, tpl, visible: used.append(tpl) or d))
    monkeypatch.setattr(docs, "K", SimpleNamespace(kPartDocumentObject=1, kMetricSystemOfMeasure=2,
                                                   kDefault_DraftingStandard=3))
    monkeypatch.setattr(docs, "_doc_info", lambda s, d: {})
    s = SimpleNamespace(app=app, stock_template=lambda name: "STOCK " + name, set_current=lambda d: None)
    docs.create_part(s)
    s.stock_template = lambda name: ""                  # not installed: the active project's template
    docs.create_part(s)
    assert used == ["STOCK Standard (mm).ipt", "PROJECT TEMPLATE"]


# ------------------------------------------------------------------ malformed MCP messages
def test_a_message_that_is_not_an_object_is_answered_not_fatal():
    from inventor_forge.server import Server
    srv = Server(visible=False)
    assert srv.handle(7)["error"]["code"] == -32600
    assert srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": [1]})["result"]["tools"]
    bad = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "status", "arguments": [1]}})
    assert bad["error"]["code"] == -32602


def test_every_saving_tool_is_listed_as_saving_in_place():
    import inspect

    from inventor_forge.fileargs import SAVES_IN_PLACE
    from inventor_forge.registry import load_all
    for name, t in load_all().items():
        src = inspect.getsource(t.fn)
        if "guarded_save(" in src or "_save(s)" in src or "save_document(s)" in src:
            assert name in SAVES_IN_PLACE, name
