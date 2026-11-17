"""Offline tests for session health: hang detection, repeated failures, the start lock, the message filter, the
PID pin and the start-up checks. No Inventor needed.

    python -m pytest tests/test_robustness.py
"""
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge import health as H  # noqa: E402
from inventor_forge.com import InventorError  # noqa: E402
from inventor_forge.registry import TOOLS, load_all  # noqa: E402

load_all()


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_busy_inventor_is_not_a_hang():
    clock, cpu = Clock(), {"v": 0.0}
    w = H.HangWatch(1, warn_s=120, stop_s=600, interval=5, hung=lambda: False, cpu=lambda: cpu["v"], clock=clock)
    for _ in range(300):                 # 25 minutes of steady work
        clock.t += 5
        cpu["v"] += 3.0
        assert w.sample() == "ok"


def test_idle_tree_warns_once_then_stops():
    clock = Clock()
    w = H.HangWatch(1, warn_s=120, stop_s=600, interval=5, hung=lambda: False, cpu=lambda: 10.0, clock=clock)
    states = []
    for _ in range(130):
        clock.t += 5
        states.append(w.sample())
    assert states.count("warn") == 1
    first_warn, first_stop = states.index("warn"), states.index("stop")
    assert 110 <= (first_warn + 1) * 5 <= 130 and 590 <= (first_stop + 1) * 5 <= 610
    assert "no CPU" in w.reason


def test_hung_window_counts_even_with_cpu_and_recovery_resets():
    clock, cpu, hung = Clock(), {"v": 0.0}, {"on": True}
    w = H.HangWatch(1, warn_s=60, stop_s=0, interval=5, hung=lambda: hung["on"], cpu=lambda: cpu["v"], clock=clock)
    for _ in range(13):
        clock.t += 5
        cpu["v"] += 5
        w.sample()
    assert w.warned and "not responding" in w.reason
    hung["on"] = False
    clock.t += 5
    cpu["v"] += 5
    assert w.sample() == "ok" and w.stuck_since is None
    for _ in range(1000):                # stop_s=0: never given up on
        clock.t += 5
        assert w.sample() != "stop"


def test_hang_limits_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("INVENTOR_FORGE_HANG_WARN", "30")
    monkeypatch.setenv("INVENTOR_FORGE_HANG_STOP", "90")
    assert H.hang_limits() == (30.0, 90.0)


def test_same_call_failing_twice_is_not_sent_a_third_time():
    import pywintypes
    from inventor_forge.engine import Forge
    from inventor_forge.registry import tool
    calls = {"n": 0}
    err = pywintypes.com_error(-2147467259, "Unspecified error", (0, "Inventor", "Feature failed", None, 0, 0), None)

    @tool("system", name="_fail_probe")
    def _fail(s, x: int = 0) -> dict:
        """Test double for an operation Inventor keeps rejecting."""
        calls["n"] += 1
        raise err

    forge = Forge()
    forge.session.solver_busy = lambda: []
    try:
        r1 = forge.safe_call("_fail_probe", {"x": 1})
        r2 = forge.safe_call("_fail_probe", {"x": 1})
        assert not r1["ok"] and "second identical failure" in r2["error"]
        r3 = forge.safe_call("_fail_probe", {"x": 1})
        assert not r3["ok"] and "failed twice in a row" in r3["error"] and calls["n"] == 2
        r4 = forge.safe_call("_fail_probe", {"x": 2})       # changed arguments go through
        assert calls["n"] == 3 and "rejected" in r4["error"]
    finally:
        TOOLS.pop("_fail_probe")


def test_start_lock_serialises_starts(tmp_path):
    path = str(tmp_path / "start.lock")
    order = []
    inside = threading.Event()

    def other():
        with H.start_lock(timeout=10, path=path):
            order.append("second")

    with H.start_lock(timeout=5, path=path):
        t = threading.Thread(target=other)
        t.start()
        t.join(1.5)
        assert t.is_alive(), "a second start went ahead while the first held the lock"
        order.append("first")
        inside.set()
    t.join(10)
    assert order == ["first", "second"]


def test_start_lock_gives_up_with_a_reason(tmp_path):
    path = str(tmp_path / "start.lock")
    with H.start_lock(timeout=5, path=path):
        result = {}

        def other():
            try:
                with H.start_lock(timeout=0.6, path=path):
                    result["got"] = True
            except InventorError as e:
                result["error"] = str(e)
        t = threading.Thread(target=other)
        t.start()
        t.join(5)
    assert "starting an Inventor" in result.get("error", "")


def test_busy_retries_until_the_limit():
    assert H.retry_delay(0, H.SERVERCALL_RETRYLATER, 60) == H.BUSY_RETRY_MS
    assert H.retry_delay(59_000, H.SERVERCALL_REJECTED, 60) == H.BUSY_RETRY_MS
    assert H.retry_delay(61_000, H.SERVERCALL_RETRYLATER, 60) == -1
    assert H.retry_delay(0, 99, 60) == -1


def test_message_filter_installs_on_a_com_thread():
    got = {}

    def run():
        import pythoncom
        pythoncom.CoInitialize()
        try:
            got["ok"] = H.register_message_filter()
        finally:
            pythoncom.CoUninitialize()
    t = threading.Thread(target=run)
    t.start()
    t.join(10)
    assert got.get("ok") is True


def test_keep_awake_is_balanced():
    with H.keep_awake(True):
        pass
    with H.keep_awake(False):
        pass


def test_session_refuses_a_different_inventor():
    from inventor_forge.session import Session
    s = Session()
    s.pinned_pid = 111
    s._process_id = staticmethod(lambda app: 222)

    import win32com.client as wc
    real = wc.GetActiveObject
    wc.GetActiveObject = lambda progid: object()
    try:
        with pytest.raises(InventorError, match="reattach"):
            s._connect()
    finally:
        wc.GetActiveObject = real
    assert s._app is None and s.pinned_pid == 111
    s.unpin()
    assert s.pinned_pid is None


def test_session_does_not_start_a_new_inventor_after_its_own_closed():
    from inventor_forge.session import Session
    import win32com.client as wc
    s = Session()
    s.pinned_pid = 111

    def none(progid):
        raise OSError("no Inventor")
    started = []
    real_get, real_ex = wc.GetActiveObject, wc.DispatchEx
    wc.GetActiveObject, wc.DispatchEx = none, lambda progid: started.append(progid)
    try:
        with pytest.raises(InventorError, match="has closed"):
            s._connect()
    finally:
        wc.GetActiveObject, wc.DispatchEx = real_get, real_ex
    assert not started


def test_start_up_checks(tmp_path):
    stop, warn = H.state_issues(r"C:\proj\A.ipj", "B", [], True, [str(tmp_path)], low_gb=0, min_gb=0)
    assert stop and "set_active_project" in stop[0]
    stop, warn = H.state_issues(r"C:\proj\A.ipj", "a", ["x.ipt"], False, [str(tmp_path)], low_gb=0, min_gb=0)
    assert not stop and "unsaved" in warn[0]
    stop, warn = H.state_issues("", "", ["x.ipt"], True, [], low_gb=0, min_gb=0)
    assert stop and "private" in stop[0]
    stop, warn = H.state_issues("", "", [], False, [str(tmp_path)], low_gb=1e9, min_gb=0)
    assert warn and "GB free" in warn[0]
    stop, warn = H.state_issues("", "", [], False, [str(tmp_path)], low_gb=1e9, min_gb=1e9)
    assert stop and "GB free" in stop[0]


def test_connect_documents_the_new_switches():
    props = TOOLS["connect"].schema["properties"]
    for k in ("private", "reattach", "expect_project", "ignore_checks"):
        assert k in props
