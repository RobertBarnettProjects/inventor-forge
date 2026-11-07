"""Escape hatch and maintenance: run Python against the live Inventor session, reload the tools."""
from __future__ import annotations

import contextlib
import importlib
import io
import sys
import traceback

from ..com import MM, K, items, typed_call
from ..registry import TOOLS, tool
from ..session import Session

_NS: dict = {}


@tool("system")
def execute_python(s: Session, code: str) -> dict:
    """Run Python in a persistent namespace with the live Inventor objects: app, doc, cdef (component
    definition or None), tg (TransientGeometry), to (TransientObjects), K (all Inventor enum constants),
    items(collection), typed_call(obj, method, ...) for [out]-parameter methods, MM (=0.1, mm->cm).
    Inventor API units are cm and radians. The value of a final expression is returned; print() output too.
    Use it for anything the dedicated tools don't cover.
    """
    app = s.app
    doc = app.ActiveDocument
    cdef = None
    if doc is not None:
        try:
            cdef = doc.ComponentDefinition
        except Exception:
            cdef = None
    _NS.update({"app": app, "doc": doc, "cdef": cdef, "tg": app.TransientGeometry, "to": app.TransientObjects,
                "K": K, "items": items, "typed_call": typed_call, "MM": MM, "session": s})
    buf = io.StringIO()
    result = None
    try:
        import ast
        tree = ast.parse(code, mode="exec")
        last = tree.body[-1] if tree.body else None
        with contextlib.redirect_stdout(buf):
            if isinstance(last, ast.Expr):
                exec(compile(ast.Module(tree.body[:-1], type_ignores=[]), "<forge>", "exec"), _NS)
                result = eval(compile(ast.Expression(last.value), "<forge>", "eval"), _NS)
            else:
                exec(compile(tree, "<forge>", "exec"), _NS)
    except Exception:
        return {"ok_python": False, "stdout": buf.getvalue()[-4000:], "error": traceback.format_exc(limit=6)[-3000:]}
    out = {"ok_python": True, "stdout": buf.getvalue()[-8000:]}
    if result is not None:
        try:
            import json
            json.dumps(result)
            out["result"] = result
        except Exception:
            out["result"] = repr(result)[:4000]
    return out


@tool("system", mutates=False)
def reload_api(s: Session) -> dict:
    """Reload the tool modules from disk (after editing them) without restarting the server."""
    pkg = __name__.rsplit(".", 2)[0]
    names = [n for n in list(sys.modules) if n.startswith(pkg + ".tools.") or n == pkg + ".uidrive"]
    before = set(TOOLS)
    TOOLS.clear()
    reloaded = []
    for n in sorted(names, key=lambda x: (x.endswith("uidrive") is False, x)):
        importlib.reload(sys.modules[n])
        reloaded.append(n.rsplit(".", 1)[-1])
    return {"reloaded": reloaded, "tools": len(TOOLS), "added": sorted(set(TOOLS) - before),
            "removed": sorted(before - set(TOOLS))}


@tool("system", mutates=False)
def list_tools(s: Session, group: str = "") -> dict:
    """Tool names by group (session, documents, sketch, features, inspect, parameters, materials,
    properties, sheet_metal, assembly, drawing, analysis, view, system)."""
    out: dict[str, list[str]] = {}
    for t in TOOLS.values():
        if group and t.group != group:
            continue
        out.setdefault(t.group, []).append(t.name)
    return {"groups": out, "count": sum(len(v) for v in out.values())}
