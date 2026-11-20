"""Offline tests for the reference audit/repair planning and the stalled-solve watcher."""
import os

from inventor_forge.stall import SolveWatch, solver_processes
from inventor_forge.tools.assembly import plan_repoints, reference_status

J = os.path.join
OLD = os.path.abspath("C:/jobs/old")
NEW = os.path.abspath("C:/jobs/new")


# ------------------------------------------------------------------ reference status
def test_status_ok_when_stored_path_exists_and_matches():
    p = J(OLD, "a.ipt")
    assert reference_status(p, p, False, exists=lambda _p: True) == "ok"


def test_status_found_elsewhere_when_stored_path_gone():
    p = J(OLD, "a.ipt")
    assert reference_status(p, J(NEW, "a.ipt"), False, exists=lambda _p: False) == "found_elsewhere"
    assert reference_status(p, "", False, exists=lambda _p: False) == "found_elsewhere"
    assert reference_status(p, p, False, stored=J(OLD, "sub", "a.ipt"), exists=lambda _p: True) == "found_elsewhere"


def test_status_order_missing_disabled_substituted():
    p = J(OLD, "a.ipt")
    assert reference_status(p, p, True, True, True) == "missing"
    assert reference_status(p, p, False, True, True) == "disabled"
    assert reference_status(p, p, False, False, True) == "substituted"


# ------------------------------------------------------------------ repoint planning
REFS = [(J(OLD, "top.iam"), J(OLD, "a.ipt")), (J(OLD, "top.iam"), J(OLD, "sub", "b.ipt")),
        (J(OLD, "sub.iam"), J(OLD, "sub", "b.ipt")), (J(OLD, "top.iam"), "C:/lib/bolt.ipt")]


def test_folder_move_keeps_relative_place():
    plan, skipped = plan_repoints(REFS, OLD + os.sep, NEW, exists=lambda _p: True, isdir=lambda _p: False)
    assert [(c) for _a, _b, c in plan] == [J(NEW, "a.ipt"), J(NEW, "sub", "b.ipt"), J(NEW, "sub", "b.ipt")]
    assert not skipped                       # the library bolt isn't under old: left alone, not skipped


def test_folder_move_skips_targets_that_dont_exist():
    have = {os.path.normcase(J(NEW, "a.ipt"))}
    plan, skipped = plan_repoints(REFS, OLD + os.sep, NEW, exists=lambda p: os.path.normcase(p) in have,
                                  isdir=lambda _p: False)
    assert len(plan) == 1 and len(skipped) == 2
    assert skipped[0]["reason"] == "the new file does not exist"


def test_bare_name_matches_any_folder():
    plan, _ = plan_repoints(REFS, "B.ipt", J(NEW, "b2.ipt"), exists=lambda _p: True, isdir=lambda _p: False)
    assert len(plan) == 2 and all(c == J(NEW, "b2.ipt") for _a, _b, c in plan)


def test_exact_path_and_no_op():
    plan, _ = plan_repoints(REFS, J(OLD, "a.ipt"), J(OLD, "a.ipt"), exists=lambda _p: True, isdir=lambda _p: False)
    assert plan == []                        # pointing a reference at itself is nothing to do
    plan, _ = plan_repoints(REFS, J(OLD, "a.ipt"), J(NEW, "a.ipt"), exists=lambda _p: True, isdir=lambda _p: False)
    assert plan == [(J(OLD, "top.iam"), J(OLD, "a.ipt"), J(NEW, "a.ipt"))]


def test_folder_prefix_does_not_match_sibling_folder():
    refs = [("t.iam", OLD + "er" + os.sep + "x.ipt")]
    plan, _ = plan_repoints(refs, OLD + os.sep, NEW, exists=lambda _p: True, isdir=lambda _p: False)
    assert plan == []


# ------------------------------------------------------------------ stalled solve watcher
def test_working_solve_never_stalls():
    w = SolveWatch(idle_s=60, hung_s=60)
    for i in range(1000):                    # solver uses 1 s of CPU per 5 s step for 5000 s
        assert w.update(i * 5.0, {1: 10.0, 2: i * 1.0}, solvers=1) == ""


def test_idle_solver_stalls_after_idle_s():
    w = SolveWatch(idle_s=60, hung_s=600)
    assert w.update(0, {1: 10.0, 2: 50.0}, solvers=1) == ""
    assert w.update(30, {1: 10.1, 2: 50.0}, solvers=1) == ""
    why = w.update(61, {1: 10.2, 2: 50.0}, solvers=1)
    assert "processor time" in why and "solver" in why


def test_solver_processes_restarting_count_as_work():
    w = SolveWatch(idle_s=60, hung_s=600)
    w.update(0, {1: 10.0, 2: 100.0}, solvers=1)
    # phase two: the first solver ended, a new one started from zero and is working
    for t in range(5, 300, 5):
        assert w.update(t, {1: 10.0, 3: t * 0.5}, solvers=1) == ""


def test_hung_inventor_stalls_after_hung_s_even_while_cpu_moves():
    w = SolveWatch(idle_s=1000, hung_s=30)
    assert w.update(0, {1: 0.0}, hung=True) == ""
    assert w.update(20, {1: 5.0}, hung=True) == ""
    assert w.update(25, {1: 10.0}, hung=False) == ""      # responded again: the clock resets
    assert w.update(40, {1: 15.0}, hung=True) == ""
    assert "not responded" in w.update(70, {1: 20.0}, hung=True)


def test_env_limits(monkeypatch):
    monkeypatch.setenv("INVENTOR_FORGE_STALL_S", "120")
    monkeypatch.setenv("INVENTOR_FORGE_HUNG_S", "nonsense")
    w = SolveWatch()
    assert w.idle_s == 120 and w.hung_s == 600


def test_solver_processes_found_through_grandchildren():
    tree = [(10, 1, "Inventor.exe"), (20, 10, "FEAComputeServer.exe"), (21, 20, "WizStress.exe"),
            (22, 20, "conhost.exe"), (30, 99, "FEAComputeServer.exe"), (40, 40, "loop.exe")]
    assert solver_processes(10, tree) == [(20, "FEAComputeServer.exe"), (21, "WizStress.exe")]
    assert solver_processes(99, tree) == [(30, "FEAComputeServer.exe")]


def test_idle_trickle_does_not_hide_a_stall():
    w = SolveWatch(idle_s=900, hung_s=600)
    why = ""
    for i in range(0, 2000, 5):             # an idle Inventor answering dialog reads: 3 ms of CPU a second
        why = why or w.update(float(i), {1: 10.0 + i * 0.003, 2: 50.0}, solvers=1)
    assert "processor time" in why


def test_slow_but_working_solve_is_not_a_stall():
    w = SolveWatch(idle_s=900, hung_s=600)
    for i in range(0, 5000, 5):             # a solver using a quarter of a core
        assert w.update(float(i), {1: 10.0, 2: i * 0.25}, solvers=1) == ""


def test_status_ok_for_a_reference_repointed_this_session():
    p = J(NEW, "a.ipt")                      # no stored relative path yet: judged by the path itself
    assert reference_status(p, p, False, stored="", exists=lambda _p: True) == "ok"
    assert reference_status(p, p, False, stored=p, exists=lambda _p: True) == "ok"
    assert reference_status(p, p, False, stored="", exists=lambda _p: False) == "found_elsewhere"
