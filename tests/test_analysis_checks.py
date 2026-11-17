"""Offline tests for the Stress Analysis read-back helpers: contacts per component, stale contacts, peak patches,
equilibrium, fast outliers, input hashes and the solve limit. No Inventor needed.

    python -m pytest tests/test_analysis_checks.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.com import InventorError  # noqa: E402
from inventor_forge.registry import TOOLS, load_all  # noqa: E402

load_all()
S = sys.modules["inventor_forge.tools.studies"]
F = sys.modules["inventor_forge.tools.fea"]


def test_contacts_per_component_and_stale_pairs():
    rows = [{"contact": "Bonded:1 [Deck:1, Lug:1]", "type": "Bonded"},
            {"contact": "Bonded:2 [Deck:1, Lug:10]", "type": "Bonded"},
            {"contact": "Separation:1 [Deck:1, Doubler:1]", "type": "Separation"}]
    comps = ["Deck:1", "Lug:1", "Lug:10", "Doubler:1", "Weld:1"]
    gaps = {("Deck:1", "Lug:10"): 5.0}
    rep = S.contact_report(rows, comps, lambda a, b: gaps.get((a, b), 0.0))
    assert len(rep["by_component"]["Deck:1"]) == 3 and len(rep["by_component"]["Lug:1"]) == 1   # Lug:1 not Lug:10
    assert rep["no_contacts"] == ["Weld:1"]
    assert [x["contact"] for x in rep["stale"]] == ["Bonded:2 [Deck:1, Lug:10]"]


def test_densest_red_patch_wins():
    pts = [(10, 10)] + [(200 + i % 5, 100 + i // 5) for i in range(25)]
    x, y, n = S.red_cluster(pts)
    assert 199 < x < 205 and 99 < y < 106 and n == 25
    assert S.red_cluster([]) is None
    assert S._reddish((200, 20, 30)) and not S._reddish((200, 180, 30)) and not S._reddish((90, 0, 0))


def test_equilibrium_from_report():
    rep = {"loads": [{"type": "Force", "vector_x": "0.000 N", "vector_y": "0.000 N", "vector_z": "-200.000 N"}],
           "reactions": [{"force_components_N": [0.0, 0.0, 200.0]}]}
    eq = S.equilibrium(rep)
    assert eq["error_pct"] == 0 and eq["ok"]
    rep["reactions"][0]["force_components_N"] = [0.0, 0.0, 120.0]
    assert "don't balance" in S.solve_checks(rep)[0]
    rep["loads"].append({"type": "Pressure", "magnitude": "1 MPa"})
    assert S.equilibrium(rep)["not_summed"] == ["Pressure"]


def test_fast_solves_are_flagged():
    rows = {"a": {"status": "done", "solve_seconds": 100}, "b": {"status": "done", "solve_seconds": 110},
            "c": {"status": "done", "solve_seconds": 20}, "d": {"status": "failed"}}
    assert S.fast_outliers(rows) == ["c"]


def test_input_hash_tracks_changes():
    a = {"geometry": "1", "parameters": {"sa_1": "100 N"}, "study": ["Loads", " Force:1"]}
    b = dict(a, parameters={"sa_1": "200 N"})
    assert S.inputs_hash(a) == S.inputs_hash(dict(a)) and S.inputs_hash(a) != S.inputs_hash(b)


def test_results_folder_and_storage(tmp_path):
    model = tmp_path / "Frame.iam"
    fea = tmp_path / "Frame" / "AIP" / "FEA"
    fea.mkdir(parents=True)
    (fea / "x.fmsh").write_bytes(b"0" * 1000)
    (fea / "x.fres").write_bytes(b"0" * 3000)
    st = S.storage(str(model))
    assert st["mesh_files"] == 1 and st["result_files"] == 1 and st["folder"] == str(fea)


def test_two_solves_at_once_is_the_limit(monkeypatch):
    U = F.U
    monkeypatch.setattr(U, "pids_named", lambda exe: [1, 2, 3])
    monkeypatch.setattr(U, "solver_windows", lambda pids: ["Simulate"] if pids[0] in (2, 3) else [])
    with pytest.raises(InventorError, match="busy"):
        F.solve_slot(1)
    monkeypatch.setenv("INVENTOR_FORGE_MAX_SOLVES", "3")
    F.solve_slot(1)


def test_new_analysis_tools():
    for n in ("list_contacts", "update_contacts", "analysis_storage", "purge_studies"):
        assert n in TOOLS
    assert "locate" in TOOLS["read_result_maximum"].schema["properties"]
    assert "skip_unchanged" in TOOLS["solve_study"].schema["properties"]
