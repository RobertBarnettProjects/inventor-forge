"""The one place file paths a tool writes to are decided: relative paths go under the session's workdir, the folder
is created, protected folders and read-only files are refused, and nothing is written in read-only mode."""
from __future__ import annotations

import contextvars
import glob
import json
import os
import tempfile

from .com import InventorError

NEEDS_MARK = "cad/needs_approval:"      # a refusal ends with this marker and a JSON list of the paths concerned
_SCOPE: contextvars.ContextVar = contextvars.ContextVar("inventor_forge_write_scope", default=None)


class NeedsApproval(InventorError):
    """A write outside the folders and files the client allowed for this call."""


def scope_from_meta(meta) -> dict | None:
    """The write scope a client sent with a call (_meta "cad/write_scope": {"dirs": [...], "files": [...]}), or None
    when it sent none (then only the protected-folder rules apply). A malformed scope allows nothing extra."""
    if not isinstance(meta, dict) or "cad/write_scope" not in meta:
        return None
    sc = meta.get("cad/write_scope")
    if not isinstance(sc, dict):
        return {"dirs": [], "files": []}
    return {k: [str(x) for x in (sc.get(k) or []) if isinstance(x, str) and x.strip()] if isinstance(sc.get(k), list)
            else [] for k in ("dirs", "files")}


def use_scope(scope: dict | None):
    """Set the write scope for the calls made in this thread; returns the token for reset_scope."""
    return _SCOPE.set(scope)


def reset_scope(token) -> None:
    _SCOPE.reset(token)


def current_scope() -> dict | None:
    return _SCOPE.get()


def _norm(p: str) -> str:
    return os.path.normcase(os.path.realpath(p))


def outside_scope(paths) -> list[str]:
    """The paths (resolved, links followed) that the current call's scope doesn't cover. Forge's own temporary files
    are always allowed. Empty when the client sent no scope."""
    sc = _SCOPE.get()
    if sc is None:
        return []
    dirs = [_norm(d) for d in sc.get("dirs") or []] + [_norm(tempfile.gettempdir())]
    files = {_norm(f) for f in sc.get("files") or []}
    out = []
    for p in paths:
        rp = _norm(p)
        if rp in files or any(rp == d or rp.startswith(d.rstrip("\\/") + os.sep) for d in dirs):
            continue
        if os.path.realpath(p) not in out:
            out.append(os.path.realpath(p))
    return out


def check_scope(paths, what: str = "write") -> None:
    """Refuse, before anything is written, when any of these paths is outside the call's scope. The refusal names
    every such path, so the client can ask the user about all of them at once and send the call again."""
    out = outside_scope(paths)
    if out:
        raise NeedsApproval(f"won't {what} {'; '.join(out)}: outside the folders this call may write to without the "
                            "user's approval. Nothing was written. Send the same call again: the client asks the user "
                            f"about these paths first.\n{NEEDS_MARK} {json.dumps(out)}")


def read_only() -> bool:
    return os.environ.get("INVENTOR_FORGE_READ_ONLY", "").strip().lower() in ("1", "true", "yes")


def protected_roots() -> list[str]:
    """Folders a model must never be written into: Autodesk's library, template and install folders, and any the
    user lists in INVENTOR_FORGE_PROTECTED (separated by ';')."""
    roots = []
    public = os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Documents", "Autodesk")
    for inv in glob.glob(os.path.join(public, "Inventor *")):      # library folders only, not the project workspace
        roots += [os.path.join(inv, sub) for sub in ("Templates", "Design Data", "Content Center Files")]
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData"):
        v = os.environ.get(env)
        if v:
            roots.append(os.path.join(v, "Autodesk"))
    roots += [x.strip() for x in os.environ.get("INVENTOR_FORGE_PROTECTED", "").split(";") if x.strip()]
    return [os.path.normcase(os.path.realpath(r_)) for r_ in roots]


def guard(path: str, what: str = "write") -> None:
    """Refuse to write into a protected folder, over a read-only file, or at all in read-only mode."""
    if read_only():
        raise InventorError(f"won't {what} {path}: this server runs read-only (INVENTOR_FORGE_READ_ONLY)")
    rp = os.path.normcase(os.path.realpath(path))
    for root in protected_roots():
        if rp == root or rp.startswith(root.rstrip("\\/") + os.sep):
            raise InventorError(f"won't {what} {path}: it is inside {root} (Autodesk's library, templates or install, "
                                "or a folder listed in INVENTOR_FORGE_PROTECTED). Save a copy elsewhere with a path")
    if os.path.exists(path) and not os.access(path, os.W_OK):
        raise InventorError(f"won't {what} {path}: the file is read-only (checked in, or a library part)")
    check_scope([path], what)


def output_path(workdir: str, path: str, sub: str, ext: str = "", what: str = "write") -> str:
    """The real path a tool writes to: relative paths under workdir/sub, the extension added when missing, the
    folder created, and the gate applied."""
    if not os.path.isabs(path):
        path = os.path.join(workdir, sub, path) if sub else os.path.join(workdir, path)
    if ext and not path.lower().endswith(ext.lower()):
        path += ext
    guard(path, what)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return path
