"""Stress and modal analysis with Inventor's own Stress Analysis environment.

Inventor's Stress Analysis has no automation API, so this drives it the way a person would:
commands are started through the API, faces are picked with a real mouse click in the viewport
(the camera is first turned to look straight at the face, which then sits under the centre of the
view), values are typed into the dialogs with the keyboard where Inventor's value boxes require it,
and the results are read back from Inventor's own stress-analysis report.

While an analysis runs it takes over the mouse and keyboard for a few seconds at a time: Inventor
must be visible on screen and nobody should touch the mouse. Every click and keystroke is checked to
land on Inventor first; otherwise the run stops with an error instead of clicking somewhere else.
"""
from __future__ import annotations

import glob
import html
import math
import os
import re
import time

from .. import uidrive as U
from ..com import InventorError, K, items, r, safe, typed_call
from ..registry import tool
from ..session import Session
from .inspect import face_centroid, face_normal

FEA_ENV = "FEA Environment Internal Name"


# --------------------------------------------------------------------------- input (mouse / keyboard)
def _pid(s: Session) -> int:
    import win32process
    return win32process.GetWindowThreadProcessId(s.app.MainFrameHWND)[1]


def _owned_by_inventor(hwnd: int, pid: int) -> bool:
    import win32process
    return bool(hwnd) and win32process.GetWindowThreadProcessId(hwnd)[1] == pid


def _bring_to_front(s: Session) -> None:
    import win32api
    import win32con
    import win32gui
    h = s.app.MainFrameHWND
    if win32gui.IsIconic(h):
        win32gui.ShowWindow(h, win32con.SW_RESTORE)
    try:     # Windows only lets the foreground process hand over focus; an Alt tap makes it allowed
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32gui.SetForegroundWindow(h)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
    except Exception:
        pass
    time.sleep(0.4)


def _click_screen(x: int, y: int, pid: int, what: str) -> None:
    import win32api
    import win32con
    import win32gui
    under = win32gui.WindowFromPoint((x, y))
    if not _owned_by_inventor(under, pid):
        raise InventorError(f"cannot click {what}: another window covers Inventor at that spot — bring Inventor "
                            "to the front, keep it unobstructed and don't use the mouse during the analysis")
    win32api.SetCursorPos((x, y))
    time.sleep(0.25)
    win32api.SetCursorPos((x + 1, y))       # a little movement so Inventor highlights what is under the cursor
    time.sleep(0.35)
    win32api.SetCursorPos((x, y))
    time.sleep(0.15)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
    time.sleep(0.4)


def _type_into(c: U.Ctrl, text: str, pid: int) -> None:
    """Inventor's value boxes ignore WM_SETTEXT, so click into the box and type like a person."""
    import win32api
    import win32con
    import win32gui
    left, top, right, bottom = win32gui.GetWindowRect(c.hwnd)
    _click_screen((left + right) // 2, (top + bottom) // 2, pid, "a dialog field")
    fg = win32gui.GetForegroundWindow()
    if not _owned_by_inventor(fg, pid):
        raise InventorError("keyboard focus left Inventor — stopping before typing anywhere else")
    keys = []
    keys += [(win32con.VK_CONTROL, 0), (ord("A"), 0), (ord("A"), 2), (win32con.VK_CONTROL, 2)]
    for ch in str(text):
        vk = win32api.VkKeyScan(ch)
        shift = (vk >> 8) & 1
        if shift:
            keys.append((win32con.VK_SHIFT, 0))
        keys += [(vk & 0xFF, 0), (vk & 0xFF, 2)]
        if shift:
            keys.append((win32con.VK_SHIFT, 2))
    keys += [(win32con.VK_TAB, 0), (win32con.VK_TAB, 2)]
    for vk, flag in keys:
        win32api.keybd_event(vk, 0, flag, 0)
        time.sleep(0.02)
    time.sleep(0.3)


# --------------------------------------------------------------------------- picking faces
def _ray_first_hit_is(s: Session, face, origin, direction) -> bool | None:
    """True if a ray from origin along direction hits `face` first (None if the API can't tell)."""
    try:
        cd = s.cdef()
        out = typed_call(cd, "FindUsingRay", s.tg.CreatePoint(*origin), s.tg.CreateUnitVector(*direction),
                         0.0001, None, None, True)
        objs = out[-2] if len(out) >= 2 else None
        if objs is None or objs.Count == 0:
            return None
        first = objs.Item(1)
        return bool(first.TransientKey == face.TransientKey)
    except Exception:
        return None


def _look_at_face(s: Session, face) -> None:
    """Point the camera straight at an interior point of the face from outside, zoomed in so the face
    fills the middle of the view and nothing else is under the centre pixel."""
    n = face_normal(face)
    p = face.PointOnFace
    dirs = [n]
    # if something blocks the straight view (a face at the bottom of a pocket), try tilted views
    for ax in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        for sgn in (1, -1):
            t = [n[i] + 0.6 * sgn * ax[i] for i in range(3)]
            ln = math.sqrt(sum(v * v for v in t))
            if ln > 1e-6 and abs(sum(t[i] * n[i] for i in range(3)) / ln) > 0.5:
                dirs.append([v / ln for v in t])
    chosen = n
    for d in dirs:
        eye = [p.X + d[0] * 100, p.Y + d[1] * 100, p.Z + d[2] * 100]
        hit = _ray_first_hit_is(s, face, eye, [-d[0], -d[1], -d[2]])
        if hit is None or hit:
            chosen = d
            break
    v = s.app.ActiveView
    cam = v.Camera
    cam.Perspective = False
    cam.Target = s.tg.CreatePoint(p.X, p.Y, p.Z)
    cam.Eye = s.tg.CreatePoint(p.X + chosen[0] * 100, p.Y + chosen[1] * 100, p.Z + chosen[2] * 100)
    up = (0, 0, 1) if abs(chosen[2]) < 0.9 else (0, 1, 0)
    cam.UpVector = s.tg.CreateUnitVector(*up)
    # zoom so roughly the face's smaller size spans a third of the view
    rb = face.Evaluator.RangeBox
    span = sorted([rb.MaxPoint.X - rb.MinPoint.X, rb.MaxPoint.Y - rb.MinPoint.Y, rb.MaxPoint.Z - rb.MinPoint.Z])
    size = max(span[1], 0.05) * 3
    safe(lambda: cam.SetExtents(size, size))
    cam.ApplyWithoutTransition()
    time.sleep(0.3)


OFFSETS = ((-0.08, 0.0), (0.08, 0.0), (0.0, -0.08), (0.0, 0.08))   # around the pick point, clear of glyphs


def _render_samples(s: Session) -> list[tuple[int, int, int]]:
    """Colours at the sample points in a small render Inventor makes of the current camera."""
    import struct
    import tempfile
    path = os.path.join(tempfile.gettempdir(), "inventor_forge_pick.bmp")
    s.app.ActiveView.SaveAsBitmap(path, 101, 61)
    with open(path, "rb") as f:
        data = f.read()
    off = struct.unpack_from("<I", data, 10)[0]
    bw, bh = struct.unpack_from("<ii", data, 18)
    bpp = struct.unpack_from("<H", data, 28)[0] // 8
    row = (bw * bpp + 3) & ~3
    out = []
    for fx, fy in OFFSETS:
        x, y = int(bw / 2 + fx * bw), int(abs(bh) / 2 + fy * abs(bh))
        if bh > 0:
            y = bh - 1 - y
        i = off + y * row + x * bpp
        out.append((data[i + 2], data[i + 1], data[i]))
    return out


def _screen_samples(s: Session) -> list[tuple[int, int, int]]:
    """Colours at the same points as actually shown on screen."""
    import win32gui
    hwnd = s.app.ActiveView.HWND
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    w, h = right - left, bottom - top
    cx, cy = win32gui.ClientToScreen(hwnd, (w // 2, h // 2))
    hdc = win32gui.GetDC(0)
    try:
        out = []
        for fx, fy in OFFSETS:
            c = win32gui.GetPixel(hdc, int(cx + fx * w), int(cy + fy * h))
            out.append((c & 255, (c >> 8) & 255, (c >> 16) & 255))
        return out
    finally:
        win32gui.ReleaseDC(0, hdc)


def _close(a, b, tol: int = 60) -> bool:
    return sum(abs(a[k] - b[k]) for k in range(3)) <= tol


def _vivid(rgb) -> bool:
    """Selection colours (green / blue) are saturated; unselected faces are grey."""
    return max(rgb) - min(rgb) >= 55


def _wait_screen_settled(s: Session, min_wait: float = 0.9, timeout: float = 5.0) -> None:
    """Inventor redraws a moment after the camera moves; wait until the pixels around the pick point
    stop changing (and at least min_wait) so the click lands on the new view, not the old one."""
    t0 = time.time()
    prev = _screen_samples(s)
    while time.time() - t0 < timeout:
        time.sleep(0.25)
        cur = _screen_samples(s)
        if time.time() - t0 >= min_wait and all(_close(a, b, 12) for a, b in zip(prev, cur)):
            return
        prev = cur


def _faces_label(dlg: int) -> str:
    try:
        return U.get_text(U.find(dlg, cid=10000))
    except InventorError:
        return ""


def _pick_face(s: Session, face, pid: int, dlg: int, attempts: int = 4) -> None:
    """Click the face in the viewport and confirm Inventor selected that face.

    Wait for the redraw after turning the camera, click the centre, move the cursor away (so the hover
    highlight disappears) and require the selection colour on screen around the pick point. A click
    that only activated Inventor's window selects nothing and is repeated; if something else got
    selected instead (the dialog says Faces but this face isn't highlighted), stop rather than add
    more faces."""
    import win32api
    import win32gui
    dl, dt, dr, db = win32gui.GetWindowRect(dlg)
    park = ((dl + dr) // 2, dt + 12)                 # the dialog's title bar
    label_before = _faces_label(dlg).lower()
    last = None
    for _ in range(attempts):
        win32api.SetCursorPos(park)
        _look_at_face(s, face)
        safe(lambda: s.app.ActiveView.Update())
        _wait_screen_settled(s)
        before = _screen_samples(s)
        if sum(_vivid(c) for c in before) >= 3:
            return                                   # already selected
        hwnd = s.app.ActiveView.HWND
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        cx, cy = win32gui.ClientToScreen(hwnd, ((right - left) // 2, (bottom - top) // 2))
        under = win32gui.WindowFromPoint((cx, cy))
        if under != hwnd and not win32gui.IsChild(hwnd, under):
            raise InventorError("the viewport centre is covered (by a dialog or another window) — cannot pick the face")
        _click_screen(cx, cy, pid, "the face in the viewport")
        win32api.SetCursorPos(park)
        time.sleep(0.8)
        last = _screen_samples(s)
        if os.environ.get("INVENTOR_FORGE_DEBUG"):
            print("pick", _faces_label(dlg), before, last)
        if sum(_vivid(c) for c in last) >= 3:
            return
        if label_before.startswith("location") and not _faces_label(dlg).lower().startswith("location"):
            raise InventorError("a different face than the requested one got selected — stopping (the view "
                                "probably hadn't redrawn yet); rerun the analysis")
    raise InventorError(f"could not confirm the face pick after {attempts} clicks (screen colours {last})")


# --------------------------------------------------------------------------- command + dialog steps
def _run_command(s: Session, name: str) -> None:
    s.app.CommandManager.ControlDefinitions.Item(name).Execute2(False)


def _front(h: int) -> None:
    import win32api
    import win32con
    import win32gui
    try:
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32gui.SetForegroundWindow(h)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
    except Exception:
        pass
    time.sleep(0.3)


def _dialog(pid: int, title, timeout: float = 20.0) -> int:
    """Wait for an Inventor dialog, park it at the left edge (clear of the viewport centre where faces
    are picked) and bring it to the front."""
    import win32con
    import win32gui
    h = U.wait_window(pid, title, timeout)
    try:
        owner = win32gui.GetWindow(h, win32con.GW_OWNER) or h
        ml, mt, mr, mb = win32gui.GetWindowRect(win32gui.GetAncestor(owner, 2))
        win32gui.SetWindowPos(h, 0, ml + 8, mt + 160, 0, 0, win32con.SWP_NOSIZE | win32con.SWP_NOZORDER)
    except Exception:
        pass
    _front(h)
    return h


def _ok(pid: int, h: int, what: str, timeout: float = 15.0) -> None:
    t0 = time.time()
    ok = U.find(h, cid=1)
    while not ok.enabled and time.time() - t0 < timeout:
        time.sleep(0.2)
        ok = U.find(h, cid=1)
    if not ok.enabled:
        U.click(U.find(h, cid=2))
        raise InventorError(f"{what}: Inventor did not accept the input (OK stayed disabled) — the face pick may "
                            "have missed; make sure Inventor is unobstructed on screen")
    U.click(ok)
    if not U.wait_gone(h, timeout):
        raise InventorError(f"{what}: dialog did not close")


def _enter_analysis(s: Session) -> None:
    env = s.app.UserInterfaceManager.Environments.Item(FEA_ENV)
    s.doc().EnvironmentManager.SetCurrentEnvironment(env)
    time.sleep(0.8)


def _create_study(s: Session, pid: int, modal_modes: int = 0) -> None:
    _run_command(s, "FeaCreateSimCmd")
    h = _dialog(pid, "Create New Study")
    if modal_modes:
        U.click(U.find(h, cid=1401))                   # Modal Analysis
        time.sleep(0.4)
        nm = U.find(h, cid=1405)                       # Number of Modes
        U.set_check(nm, True)
        time.sleep(0.3)
        _type_into(U.find(h, cid=1409), str(int(modal_modes)), pid)
    else:
        U.click(U.find(h, cid=1402))                   # Static Analysis
    _ok(pid, h, "Create Study")
    time.sleep(0.8)


def _fixed(s: Session, pid: int, faces: list) -> None:
    _run_command(s, "FeaCreateConstrFixedCmd")
    h = _dialog(pid, "Fixed Constraint")
    for f in faces:
        _pick_face(s, f, pid, h)
    _ok(pid, h, "Fixed Constraint")


def _force(s: Session, pid: int, face, vec) -> None:
    _run_command(s, "FeaCreateLoadForceCmd")
    h = _dialog(pid, "Force")
    _pick_face(s, face, pid, h)
    U.set_check(U.find(h, cid=1225), True)              # Use Vector Components
    time.sleep(0.4)
    for cid, v in zip((1216, 1215, 1220), vec):
        _type_into(U.find(h, cid=cid), f"{float(v):g}", pid)
    _ok(pid, h, "Force")


def _pressure(s: Session, pid: int, face, mpa: float) -> None:
    _run_command(s, "FeaCreateLoadPressureCmd")
    h = _dialog(pid, "Pressure")
    _pick_face(s, face, pid, h)
    _type_into(U.find(h, cid=10015), f"{float(mpa):g} MPa", pid)
    _ok(pid, h, "Pressure")


def _gravity(s: Session, pid: int, g=(0.0, 0.0, -9810.0)) -> None:
    _run_command(s, "FeaCreateLoadGravityCmd")
    h = _dialog(pid, "Gravity")
    U.set_check(U.find(h, cid=1225), True)
    time.sleep(0.4)
    for cid, v in zip((1216, 1215, 1220), g):
        _type_into(U.find(h, cid=cid), f"{float(v):g}", pid)
    _ok(pid, h, "Gravity")


def _mesh(s: Session, pid: int, avg_fraction: float) -> None:
    _run_command(s, "FeaMeshSettingCmd")
    h = _dialog(pid, "Mesh Settings")
    _type_into(U.find(h, cid=10081), f"{avg_fraction:g}", pid)
    _ok(pid, h, "Mesh Settings")


def _simulate(s: Session, pid: int, timeout: float = 900.0) -> float:
    import win32gui
    _run_command(s, "FeaSimulateCmd")
    h = _dialog(pid, "Simulate")
    t0 = time.time()
    U.click(U.find(h, cid=1))                          # Run
    # the dialog closes when the solve finishes (or immediately for small models); also watch for a
    # separate progress window
    while time.time() - t0 < timeout:
        busy = False
        for w in U.process_windows(pid):
            try:
                if win32gui.GetClassName(w) == "#32770" and "simulat" in win32gui.GetWindowText(w).lower():
                    busy = True
            except Exception:
                continue
        if not busy:
            break
        time.sleep(0.5)
    time.sleep(1.0)
    return time.time() - t0


def _report(s: Session, pid: int, name: str, timeout: float = 120.0) -> str:
    _run_command(s, "FeaGenerateReportCmd")
    h = _dialog(pid, "Report")
    U.set_text(U.find(h, cid=10110), name)             # file name (a plain edit box)
    started = time.time()
    prompts_before = _openwith_pids()
    U.click(U.find(h, cid=1))
    U.wait_gone(h, 30)
    _close_open_with_prompts(prompts_before)
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    folders = [os.path.join(docs, "Inventor"), docs]
    proj = safe(lambda: s.app.DesignProjectManager.ActiveDesignProject.WorkspacePath, "")
    if proj:
        folders.insert(0, proj)
    part_dir = os.path.dirname(safe(lambda: s.doc().FullFileName, "") or "")
    if part_dir:
        folders.insert(0, part_dir)
    t0 = time.time()
    while time.time() - t0 < timeout:
        for fo in folders:
            for p in glob.glob(os.path.join(fo, "**", name + ".htm*"), recursive=True) if os.path.isdir(fo) else []:
                if os.path.getmtime(p) >= started - 2:
                    time.sleep(1.0)
                    return p
        time.sleep(0.5)
    raise InventorError("Inventor's stress report was not found after generating it")


def _openwith_pids() -> set[int]:
    import ctypes
    import win32api
    import win32process
    out = set()
    for pid in win32process.EnumProcesses():
        try:
            hp = win32api.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        except Exception:
            continue
        try:
            buf = ctypes.create_unicode_buffer(512)
            size = ctypes.c_ulong(512)
            ctypes.windll.kernel32.QueryFullProcessImageNameW(int(hp.handle), 0, buf, ctypes.byref(size))
            if os.path.basename(buf.value).lower() == "openwith.exe":
                out.add(pid)
        finally:
            win32api.CloseHandle(hp)
    return out


def _close_open_with_prompts(existing: set[int], wait: float = 6.0) -> int:
    """Inventor opens the finished report with the .html handler; when Windows has none it starts an
    'Open with' chooser (OpenWith.exe) that sits over Inventor and would block the next clicks. End only
    choosers that appeared during this step (not ones that were already there)."""
    import win32api
    import win32process
    closed = 0
    t0 = time.time()
    while time.time() - t0 < wait:
        for pid in _openwith_pids() - existing:
            try:
                hp = win32api.OpenProcess(0x0001, False, pid)    # PROCESS_TERMINATE
                win32process.TerminateProcess(hp, 0)
                win32api.CloseHandle(hp)
                closed += 1
            except Exception:
                pass
        if closed:
            break
        time.sleep(0.5)
    return closed


# --------------------------------------------------------------------------- report parsing
def _report_text(path: str) -> list[str]:
    with open(path, encoding="utf-8", errors="replace") as f:
        t = f.read()
    t = re.sub(r"<script.*?</script>|<style.*?</style>|<img[^>]*>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</tr>|</p>|</h\d>|</div>", "\n", t, flags=re.I)
    t = re.sub(r"</td>|</th>", "\n", t, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return [re.sub(r"\s+", " ", ln).strip() for ln in t.splitlines() if ln.strip()]


def _num(text: str) -> float | None:
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", text.replace(",", ""))
    return float(m.group(1)) if m else None


def parse_report(path: str, study: str = "") -> dict:
    """Parse one study of an Inventor stress report (the report lists every study in the document;
    by default the last one, i.e. the study just run)."""
    lines = _report_text(path)
    heads = [i for i, ln in enumerate(lines) if re.match(r"^(Static|Modal) Analysis:\d+$", ln)]
    if heads:
        pick = [i for i in heads if lines[i] == study] if study else []
        start = pick[0] if pick else heads[-1]
        nxt = [i for i in heads if i > start]
        name = lines[start]
        lines = lines[start:nxt[0] if nxt else len(lines)]
    else:
        name = ""
    out: dict = {"study": name, "summary": {}, "reactions": [], "loads": [], "material": {}}
    if "Avg. Element Size (fraction of model diameter)" in lines:
        k = lines.index("Avg. Element Size (fraction of model diameter)")
        out["mesh_avg_size_fraction"] = _num(lines[k + 1])
    try:
        i = lines.index("Result Summary")
    except ValueError:
        i = -1
    if i >= 0:
        j = i + 1
        while j < len(lines) and lines[j] in ("Name", "Minimum", "Maximum"):
            j += 1
        while j + 2 < len(lines) and lines[j] not in ("Figures",):
            name, lo, hi = lines[j], lines[j + 1], lines[j + 2]
            if _num(lo) is None or _num(hi) is None:
                if _num(lo) is not None:            # single-value rows (Volume, Mass)
                    out["summary"][name] = {"value": _num(lo), "unit": lo.split()[-1] if " " in lo else ""}
                    j += 2
                    continue
                j += 1
                continue
            unit = hi.split()[-1] if " " in hi else ""
            out["summary"][name] = {"min": _num(lo), "max": _num(hi), "unit": unit}
            j += 3
    # material block
    for key, label in (("Yield Strength", "yield_MPa"), ("Young's Modulus", "E"), ("Poisson's Ratio", "poisson"),
                       ("Mass Density", "density")):
        if key in lines:
            k = lines.index(key)
            out["material"][label] = lines[k + 1]
    if "Name" in lines:
        k = lines.index("Name")
        out["material"]["name"] = lines[k + 1] if k + 1 < len(lines) else ""
    # reactions: rows start with "<constraint name>:" then magnitude
    if "Reaction Force and Moment on Constraints" in lines:
        k = lines.index("Reaction Force and Moment on Constraints") + 1
        while k < len(lines) and lines[k] != "Result Summary":
            if re.match(r".+:\d+$", lines[k]) and k + 1 < len(lines) and lines[k + 1].endswith(" N"):
                vals = lines[k + 1:k + 9]
                forces = [_num(v) for v in vals if v.endswith(" N")]
                moments = [_num(v) for v in vals if v.endswith(" N m")]
                out["reactions"].append({"constraint": lines[k], "force_N": forces[0] if forces else None,
                                         "force_components_N": forces[1:4], "moment_Nm": moments[0] if moments else None,
                                         "moment_components_Nm": moments[1:4]})
                k += 9
            else:
                k += 1
    # loads echo
    for k, ln in enumerate(lines):
        if ln == "Load Type" and k + 1 < len(lines):
            entry = {"type": lines[k + 1]}
            for m in range(k + 2, min(k + 14, len(lines) - 1)):
                if lines[m] in ("Magnitude", "Vector X", "Vector Y", "Vector Z"):
                    entry[lines[m].lower().replace(" ", "_")] = lines[m + 1]
            out["loads"].append(entry)
    # modal frequencies (rows like "F1" / "Frequency 1" followed by "123.4 Hz")
    freqs = []
    for k, ln in enumerate(lines[:-1]):
        if re.match(r"^(F\d+|Frequency\s*\d+|Mode\s*\d+)$", ln) and lines[k + 1].endswith("Hz"):
            freqs.append(_num(lines[k + 1]))
    if freqs:
        out["frequencies_Hz"] = freqs
    return out


# --------------------------------------------------------------------------- tools
def _check_ready(s: Session) -> None:
    d = s.part()
    if s.cdef().SurfaceBodies.Count == 0:
        raise InventorError("the part has no solid body")
    if safe(lambda: d.ActiveMaterial.DisplayName, "Generic") in ("Generic", "", None):
        raise InventorError("assign a material first (set_material) — Inventor's Generic material has no strength data")


KBM_NOTICE = (
    "Heads-up: Inventor's Stress Analysis has no automation API, so this analysis is run by TAKING OVER YOUR "
    "MOUSE AND KEYBOARD for about 30-60 seconds. Inventor will come to the front, its camera will move, faces "
    "will be clicked and dialogs filled in automatically. Please save your work in other apps, keep Inventor "
    "visible and unobstructed, and don't touch the mouse or keyboard until it finishes. Any click that would "
    "land outside Inventor stops the run. Reply 'go' (or similar) when ready."
)


def _notice_gate(user_notified: bool, what: str) -> dict | None:
    if user_notified:
        return None
    return {"status": "needs_user_go_ahead", "notice": KBM_NOTICE,
            "next": f"Nothing has run yet. Show the notice to the user word for word, wait for their go-ahead, then "
                    f"call {what} again with the same arguments plus user_notified=true."}


@tool("analysis")
def analyze_stress(s: Session, fixed_faces: list[int], loads: list[dict] | None = None, gravity: bool = False,
                   mesh_fraction: float = 0.0, name: str = "", user_notified: bool = False) -> dict:
    """Static stress analysis in Inventor's own Stress Analysis environment. TAKES OVER THE MOUSE AND
    KEYBOARD for the duration (faces are picked in the viewport; Inventor must be visible and nobody should
    touch the mouse). Creates a study, fixes the faces, applies the loads, simulates, and reads Inventor's
    stress report: max von Mises and principal stresses, max displacement, min safety factor, reactions
    (equilibrium check against the applied loads), plus a picture of the stress plot.

    fixed_faces: face indices (list_faces) held fixed
    loads: [{"face": 5, "force": [0, 0, -200]} (N, total)  or  {"face": 5, "pressure": 2.0} (MPa)]
    gravity: add self-weight in -Z
    mesh_fraction: Inventor's average element size as a fraction of the bounding box (default 0.1;
      0.05 is finer and slower) — run twice with two values to check convergence
    user_notified: must be true to run. Without it nothing happens and the tool returns a notice that you
      must show the user (mouse + keyboard takeover) and get their go-ahead for first.
    """
    gate = _notice_gate(user_notified, "analyze_stress")
    if gate:
        return gate
    if not fixed_faces:
        raise InventorError("give at least one fixed face")
    loads = loads or []
    if not loads and not gravity:
        raise InventorError("no loads — give loads=[...] and/or gravity=true")
    _check_ready(s)
    fixed = [s.face(i) for i in fixed_faces]
    load_faces = [(s.face(int(ld["face"])), ld) for ld in loads]
    pid = _pid(s)
    applied = [0.0, 0.0, 0.0]
    tag = name or f"forge_{time.strftime('%H%M%S')}"
    t0 = time.time()
    _bring_to_front(s)
    _enter_analysis(s)
    _create_study(s, pid)
    if mesh_fraction:
        _mesh(s, pid, mesh_fraction)
    _fixed(s, pid, fixed)
    for face, ld in load_faces:
        if ld.get("force"):
            vec = [float(v) for v in ld["force"]]
            _force(s, pid, face, vec)
            applied = [applied[i] + vec[i] for i in range(3)]
        elif ld.get("pressure"):
            p = float(ld["pressure"])
            _pressure(s, pid, face, p)
            n = face_normal(face)
            area = face.Evaluator.Area * 100
            if face.SurfaceType == K.kPlaneSurface:
                applied = [applied[i] - p * area * n[i] for i in range(3)]
            else:
                applied = None if applied is None else applied   # curved: resultant not tracked
        else:
            raise InventorError(f"load needs force or pressure: {ld}")
    if gravity:
        _gravity(s, pid)
        w = s.cdef().MassProperties.Mass * 9.81
        if applied is not None:
            applied[2] -= w
    solve_s = _simulate(s, pid)
    report = _report(s, pid, tag)
    res = parse_report(report)
    sm = res["summary"]

    def mx(key, field="max"):
        return (sm.get(key) or {}).get(field)

    out = {"engine": "Autodesk Inventor Stress Analysis", "study": res.get("study") or "Static Analysis",
           "mesh_avg_size_fraction": res.get("mesh_avg_size_fraction"),
           "max_von_mises_MPa": mx("Von Mises Stress"),
           "max_principal_MPa": mx("1st Principal Stress"), "min_principal_MPa": mx("3rd Principal Stress", "min"),
           "max_displacement_mm": mx("Displacement"),
           "safety_factor_min": mx("Safety Factor", "min"),
           "reactions": res["reactions"], "loads_echo": res["loads"], "material": res["material"],
           "report": report, "solve_seconds": r(solve_s, 1), "total_seconds": r(time.time() - t0, 1)}
    y = _num(res["material"].get("yield_MPa", "") or "")
    if y and out["max_von_mises_MPa"]:
        out["safety_factor_yield"] = r(y / out["max_von_mises_MPa"], 3)
    if applied is not None and res["reactions"]:
        rf = [sum((rc.get("force_components_N") or [0, 0, 0])[k] or 0 for rc in res["reactions"]) for k in range(3)]
        mag = math.sqrt(sum(a * a for a in applied)) or 1e-9
        out["applied_load_N"] = [r(v, 3) for v in applied]
        out["reaction_N"] = [r(v, 3) for v in rf]
        out["equilibrium_error_pct"] = r(100 * math.sqrt(sum((rf[k] + applied[k]) ** 2 for k in range(3))) / mag, 3)
    # independent check that the right faces were picked: the reaction moment at a single fixed face
    # must equal the moment of the applied forces about that face's centre
    force_loads = [(f, ld) for f, ld in load_faces if ld.get("force")]
    if len(fixed) == 1 and force_loads and len(force_loads) == len(load_faces) and not gravity and res["reactions"]:
        c0 = face_centroid(fixed[0])
        m = [0.0, 0.0, 0.0]
        for f, ld in force_loads:
            c = face_centroid(f)
            rv = [(c[i] - c0[i]) / 1000.0 for i in range(3)]          # m
            fv = [float(v) for v in ld["force"]]
            m = [m[0] + rv[1] * fv[2] - rv[2] * fv[1], m[1] + rv[2] * fv[0] - rv[0] * fv[2],
                 m[2] + rv[0] * fv[1] - rv[1] * fv[0]]
        expected = math.sqrt(sum(v * v for v in m))
        got = res["reactions"][0].get("moment_Nm") or 0.0
        out["moment_check"] = {"expected_Nm": r(expected, 4), "reaction_Nm": r(got, 4)}
        if abs(got - expected) > 0.05 * max(expected, 1e-6) + 0.01:
            out["warning"] = ("the reaction moment does not match the loads on the faces you asked for — a face pick "
                              "probably went to the wrong face; do not use these results, rerun the analysis")
            out["moment_check"]["ok"] = False
        else:
            out["moment_check"]["ok"] = True
    png = os.path.join(s.workdir, "renders", f"{tag}_von_mises.png")
    os.makedirs(os.path.dirname(png), exist_ok=True)
    safe(lambda: _iso_result_view(s))
    safe(lambda: s.app.ActiveView.SaveAsBitmap(png, 1600, 1000))
    if os.path.exists(png):
        out["path"] = png
    out["note"] = ("Inventor's default mesh is coarse; rerun with mesh_fraction=0.05 and compare the peak to "
                   "check convergence. The results stay in Inventor's Stress Analysis environment.")
    return out


def _iso_result_view(s: Session) -> None:
    cam = s.app.ActiveView.Camera
    cam.ViewOrientationType = K.kIsoTopRightViewOrientation
    cam.Fit()
    cam.ApplyWithoutTransition()


@tool("analysis")
def analyze_modes(s: Session, fixed_faces: list[int], modes: int = 6, name: str = "",
                  user_notified: bool = False) -> dict:
    """Natural frequencies with Inventor's Stress Analysis (modal study). TAKES OVER THE MOUSE AND KEYBOARD
    while it runs (faces are picked in the viewport). Returns the frequencies from Inventor's report.
    Needs user_notified=true (see analyze_stress)."""
    gate = _notice_gate(user_notified, "analyze_modes")
    if gate:
        return gate
    if not fixed_faces:
        raise InventorError("give at least one fixed face")
    _check_ready(s)
    fixed = [s.face(i) for i in fixed_faces]
    pid = _pid(s)
    tag = name or f"forge_modal_{time.strftime('%H%M%S')}"
    _bring_to_front(s)
    _enter_analysis(s)
    _create_study(s, pid, modal_modes=int(modes))
    _fixed(s, pid, fixed)
    solve_s = _simulate(s, pid)
    report = _report(s, pid, tag)
    res = parse_report(report)
    freqs = res.get("frequencies_Hz", [])
    return {"engine": "Autodesk Inventor Stress Analysis", "study": res.get("study") or "Modal Analysis",
            "frequencies_Hz": freqs[:int(modes)] if len(freqs) >= int(modes) else freqs,
            "all_frequencies_Hz": freqs, "mesh_avg_size_fraction": res.get("mesh_avg_size_fraction"),
            "report": report, "solve_seconds": r(solve_s, 1)}


@tool("analysis")
def exit_analysis(s: Session) -> dict:
    """Leave Inventor's Stress Analysis environment and return to modelling."""
    d = s.doc()
    base = d.EnvironmentManager.BaseEnvironment
    d.EnvironmentManager.SetCurrentEnvironment(base)
    return {"environment": safe(lambda: base.InternalName, "base")}


@tool("analysis", mutates=False)
def read_stress_report(s: Session, path: str) -> dict:
    """Parse an Inventor Stress Analysis HTML report (results summary, reactions, loads, material)."""
    if not os.path.exists(path):
        raise InventorError(f"no such report: {path}")
    return parse_report(path)
