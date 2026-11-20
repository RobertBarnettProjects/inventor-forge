"""Telling a stalled Stress Analysis solve from a slow one, from Windows only (no COM calls during a solve).

A solve runs in Inventor and in solver processes it starts (FEAComputeServer.exe, and WizStress.exe on some
versions). While any of them uses processor time the solve is working, however long it takes. A solve has stalled
when none of them has used any for a long while, or when Inventor itself has stopped responding to Windows for a long
while. Waiting out the whole time limit (an hour by default) for either is what this avoids.

The watcher is plain logic fed with samples, so it is tested without Inventor; ``sample`` reads the samples.
"""
from __future__ import annotations

import os

SOLVER_EXES = ("feacomputeserver.exe", "wizstress.exe")
IDLE_S = 900.0          # no processor time used by Inventor or its solvers for this long: stalled
HUNG_S = 600.0          # Inventor not responding to Windows for this long: stalled
MIN_CPU_S = 2.0         # processor seconds that count as work (reading the dialog costs Inventor a little)
IDLE_SHARE = 0.01       # ... or 1 % of one core over the idle window, whichever is more


def _env(name: str, default: float) -> float:
    try:
        v = float(os.environ.get(name, "") or default)
    except ValueError:
        return default
    return v if v > 0 else default


class SolveWatch:
    """Fed ``update(t, cpu, hung)`` about once a second; returns why the solve has stalled, or "" while it hasn't.

    cpu: {process id: processor seconds so far} for Inventor and every solver process it has started. A process that
      appears counts from zero, so solver processes that come and go between solve phases are handled.
    hung: Inventor's main window is not responding to Windows.
    """

    def __init__(self, idle_s: float | None = None, hung_s: float | None = None, min_cpu_s: float = MIN_CPU_S):
        self.idle_s = idle_s if idle_s is not None else _env("INVENTOR_FORGE_STALL_S", IDLE_S)
        self.hung_s = hung_s if hung_s is not None else _env("INVENTOR_FORGE_HUNG_S", HUNG_S)
        # work over the last idle_s that counts as a solve working: a solver keeps at least one core busy, while an
        # idle Inventor answering the dialog reads trickles a few ms a second, which must not keep a stall alive
        self.need_s = max(min_cpu_s, IDLE_SHARE * self.idle_s)
        self.last: dict[int, float] = {}
        self.window: list[tuple[float, float]] = []      # (time, processor seconds used since the sample before)
        self.started: float | None = None
        self.hung_since: float | None = None
        self.solvers_seen = False

    def update(self, t: float, cpu: dict[int, float], hung: bool = False, solvers: int = 0) -> str:
        if self.started is None:
            self.started = t
        used = 0.0
        for pid, secs in cpu.items():
            before = self.last.get(pid, 0.0)
            if secs > before:
                used += secs - before
            self.last[pid] = secs
        self.window.append((t, used))
        self.window = [(ts, u) for ts, u in self.window if t - ts < self.idle_s]
        self.solvers_seen = self.solvers_seen or solvers > 0
        self.hung_since = (self.hung_since if self.hung_since is not None else t) if hung else None
        if self.hung_since is not None and t - self.hung_since >= self.hung_s:
            return f"Inventor has not responded to Windows for {t - self.hung_since:.0f} s"
        recent = sum(u for _ts, u in self.window)
        if t - self.started >= self.idle_s and recent < self.need_s:
            who = "Inventor and its solver processes" if self.solvers_seen else "Inventor (no solver process started)"
            return (f"{who} used {recent:.1f} s of processor time in the last {self.idle_s:.0f} s "
                    f"(a working solve uses far more)")
        return ""


def solver_processes(inventor_pid: int, tree: list[tuple[int, int, str]] | None = None) -> list[tuple[int, str]]:
    """(pid, exe) of solver processes started by this Inventor, directly or through another process.

    tree: [(pid, parent pid, exe)] of every process (read from Windows when not given)."""
    if tree is None:
        tree = _process_table()
    children: dict[int, list[tuple[int, str]]] = {}
    for pid, parent, exe in tree:
        if pid != parent:
            children.setdefault(parent, []).append((pid, exe))
    out, todo, seen = [], [inventor_pid], {inventor_pid}
    while todo:
        for pid, exe in children.get(todo.pop(), []):
            if pid in seen:
                continue
            seen.add(pid)
            todo.append(pid)
            if exe.lower() in SOLVER_EXES:
                out.append((pid, exe))
    return out


def orphaned(solvers: list[int], inventors: set[int], parents: dict[int, int]) -> list[int]:
    """The solver processes that no running Inventor started, directly or through other processes.

    solvers: solver process ids; inventors: the running Inventors' ids; parents: {pid: parent pid} of every process.
    A solver with a running Inventor anywhere above it is in use (it may be the user's solve) and is never listed."""
    out = []
    for pid in solvers:
        cur, seen = pid, set()
        while cur in parents and cur not in seen and cur not in inventors:
            seen.add(cur)
            cur = parents[cur]
        if cur not in inventors:
            out.append(pid)
    return out


def _process_table() -> list[tuple[int, int, str]]:
    """[(pid, parent pid, exe name)] of every process, from one Toolhelp snapshot."""
    import ctypes
    from ctypes import wintypes as wt

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                    ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]
    k = ctypes.WinDLL("kernel32", use_last_error=True)     # its own prototypes: handles are pointer-sized
    k.CreateToolhelp32Snapshot.restype = wt.HANDLE
    k.CreateToolhelp32Snapshot.argtypes = (wt.DWORD, wt.DWORD)
    for f in (k.Process32FirstW, k.Process32NextW):
        f.restype, f.argtypes = wt.BOOL, (wt.HANDLE, ctypes.POINTER(Entry))
    k.CloseHandle.restype, k.CloseHandle.argtypes = wt.BOOL, (wt.HANDLE,)
    snap = k.CreateToolhelp32Snapshot(0x2, 0)              # TH32CS_SNAPPROCESS
    if snap in (None, wt.HANDLE(-1).value):
        raise OSError("Windows gave no process list")
    out = []
    try:
        e = Entry()
        e.dwSize = ctypes.sizeof(Entry)
        ok = k.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out.append((e.th32ProcessID, e.th32ParentProcessID, e.szExeFile))
            ok = k.Process32NextW(snap, ctypes.byref(e))
    finally:
        k.CloseHandle(snap)
    return out


def inventor_hung(pid: int) -> bool:
    """Is any visible top-level window of this Inventor marked not responding by Windows?"""
    import ctypes

    import win32gui

    from . import uidrive as U
    user32 = ctypes.windll.user32
    for h in U.process_windows(pid):
        if win32gui.IsWindowVisible(h) and not win32gui.GetParent(h) and win32gui.GetWindowText(h) \
                and user32.IsHungAppWindow(h):
            return True
    return False


def sample(inventor_pid: int) -> tuple[dict[int, float], bool, list[tuple[int, str]]]:
    """({pid: processor seconds} for Inventor and its solvers, Inventor hung?, the solver processes)."""
    from . import uidrive as U
    solvers = solver_processes(inventor_pid)
    cpu = {}
    for pid in [inventor_pid] + [p for p, _exe in solvers]:
        try:
            cpu[pid] = U.process_stats(pid)["cpu_seconds"]
        except Exception:  # noqa: BLE001 - the process ended between the snapshot and the read
            pass
    try:
        hung = inventor_hung(inventor_pid)
    except Exception:  # noqa: BLE001
        hung = False
    return cpu, hung, solvers
