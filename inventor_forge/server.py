"""MCP server (stdio, JSON-RPC 2.0, no third-party dependencies).

    python -m inventor_forge.server            # Claude Code / Claude Desktop / any MCP client
    python -m inventor_forge.server --hidden   # start Inventor invisibly if it isn't running

Tool results are JSON text; screenshot / render_sheet results also carry the PNG as an image block
so the model can look at its own work.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
import time
import traceback

from . import __version__
from .com import InventorError
from .writes import reset_scope, scope_from_meta, use_scope
from .engine import Forge, tool_enabled
from .profile import PROGRESS_EVERY, server_profile, tool_meta
from .registry import DESTRUCTIVE

PROTOCOL = "2025-06-18"
GUIDE_URI = "inventor-forge://guide/"
IMAGE_TOOLS = {"screenshot", "render_sheet"}
INSTRUCTIONS = (
    "Autodesk Inventor over COM. All lengths mm, angles degrees, forces N, stresses MPa. "
    "Parts: create_part -> create_sketch -> draw_* -> extrude/revolve -> hole/fillet/... ; every feature "
    "returns a volume delta — check it against your own hand calculation. Face/edge indices come from "
    "list_faces / list_edges / find_face / find_edge and change after features. Drawings: make_part_sheet or "
    "make_assembly_sheet, then check_drawing until TOTAL ISSUES: 0, render_sheet to look, export_pdf. "
    "Analysis: analyze_stress / analyze_modes run Inventor's own Stress Analysis and TAKE OVER THE USER'S MOUSE "
    "AND KEYBOARD while they run (faces by list_faces index). Always show the user the notice the tool returns "
    "and wait for their go-ahead before calling again with user_notified=true. Once a study exists, copy_study, "
    "set_analysis_parameters, solve_study, read_result_maximum and run_study_cases need no mouse: build a template, then sweep it. "
    "Don't call Inventor during a solve; solve_state is safe. connect(private=true) gives this session its own Inventor when the "
    "user has theirs open. "
    "Standards: at the start of a chat call get_standard; if the user hasn't chosen one, ask them once which to work "
    "to (list_standards: AS 1100, ISO, ASME, DIN, BS 8888, JIS, GB), then set_standard. It holds for the rest of the "
    "session: drawings, fastener and material choices follow it. execute_python is the escape hatch. "
    "guide(topic) holds the rules learned about Inventor (session, modelling, assemblies, stress-analysis, drawings, "
    "printing): read the topic before that kind of work. Multi-body parts: give body= to cuts, holes, fillets and "
    "chamfers. A call that fails the same way twice is not sent a third time: change something first."
)


class Server:
    def __init__(self, visible: bool = True, emit=None, lock=None):
        self.forge = Forge(visible=visible)
        self.emit = emit or (lambda msg, alive=None: None)   # sends a notification to the client (thread-safe)
        self.lock = lock or threading.Lock()                  # the writer's lock

    def finish(self) -> None:
        """Close the private Inventor this session started (left open and shown if it holds unsaved changes)."""
        from .tools.docs import finish_session
        try:
            # on the thread that owns the session's COM objects: they can't be used from this one
            out = self.forge.apartment.submit(lambda: finish_session(self.forge.session)).result(timeout=150)
            if out.get("left_open"):
                print(f"inventor-forge: left Inventor {out['left_open']} open: unsaved {out.get('unsaved')}",
                      file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"inventor-forge: closing the session's Inventor failed: {e}", file=sys.stderr)

    def tools_list(self) -> list[dict]:
        out = []
        for t in self.forge.tools.values():
            if not tool_enabled(t):
                continue
            out.append({"name": t.name, "description": t.description, "inputSchema": t.schema,
                        "annotations": {"readOnlyHint": not t.mutates,
                                        "destructiveHint": t.name in DESTRUCTIVE},
                        "_meta": tool_meta(t)})
        return out

    def _heartbeat(self, name: str, token, stop: threading.Event) -> None:
        """MCP progress notifications while a call runs: the client knows the server is alive and working, and can
        show what it is doing (a long solve sets session.progress), instead of guessing from a fixed timeout."""
        t0 = time.monotonic()
        n = 0
        while not stop.wait(PROGRESS_EVERY):
            n += 1
            elapsed = time.monotonic() - t0
            doing = str(getattr(self.forge.session, "progress", "") or "").strip()
            # sent only while the call is still running, checked under the writer's lock, so a progress
            # notification can never follow the call's own reply
            self.emit({"jsonrpc": "2.0", "method": "notifications/progress",
                       "params": {"progressToken": token, "progress": n,
                                  "message": f"{name}: {doing or 'working'} ({elapsed:.0f} s)"}},
                      alive=lambda: not stop.is_set())

    def tools_call(self, name: str, args: dict, token=None, scope: dict | None = None) -> dict:
        """scope: the folders and files this call may write to (the client's "cad/write_scope"); None = no limit
        beyond the protected folders."""
        stop = threading.Event()
        if token is not None:
            threading.Thread(target=self._heartbeat, args=(name, token, stop), daemon=True).start()
        mark = use_scope(scope)
        try:
            return self._tools_call(name, args)
        finally:
            reset_scope(mark)
            with self.lock:                # no heartbeat is mid-write once this is set
                stop.set()
            try:
                self.forge.session.progress = ""
            except Exception:
                pass

    def _tools_call(self, name: str, args: dict) -> dict:
        try:
            res = self.forge.call(name, args)
            content = [{"type": "text", "text": json.dumps(res, ensure_ascii=False, default=str)}]
            if name in IMAGE_TOOLS:
                paths = [res.get("path", "")] + [i.get("path", "") for i in res.get("images") or []]
                for pth in [x for x in paths if x and x.lower().endswith(".png") and os.path.exists(x)][:6]:
                    if os.path.getsize(pth) < 4_000_000:
                        with open(pth, "rb") as f:
                            content.append({"type": "image", "mimeType": "image/png",
                                            "data": base64.b64encode(f.read()).decode()})
            return {"content": content, "isError": False}
        except InventorError as e:
            return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
        except Exception as e:  # noqa: BLE001
            tb = traceback.format_exc(limit=5)[-1500:]
            return {"content": [{"type": "text", "text": f"Error: {type(e).__name__}: {e}\n{tb}"}], "isError": True}

    def handle(self, msg: dict) -> dict | None:
        if not isinstance(msg, dict):          # not a JSON-RPC message: answered, never allowed to stop the server
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
        mid = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if mid is None:          # notification
            return None
        try:
            if method == "initialize":
                result = {"protocolVersion": params.get("protocolVersion", PROTOCOL),
                          "capabilities": {"tools": {"listChanged": False}, "resources": {},
                                           "experimental": {"cad/profile": server_profile()}},
                          "serverInfo": {"name": "inventor-forge", "version": __version__},
                          "instructions": INSTRUCTIONS}
            elif method == "tools/list":
                result = {"tools": self.tools_list()}
            elif method == "tools/call":
                meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
                args = params.get("arguments") or {}
                if not isinstance(args, dict):
                    return {"jsonrpc": "2.0", "id": mid,
                            "error": {"code": -32602, "message": "tools/call arguments must be an object"}}
                result = self.tools_call(str(params.get("name", "")), args, meta.get("progressToken"),
                                         scope_from_meta(meta))
            elif method == "ping":
                result = {}
            elif method == "resources/list":
                from . import guides
                result = {"resources": [{"uri": f"{GUIDE_URI}{k}", "name": f"guide: {k}", "description": v,
                                         "mimeType": "text/markdown"} for k, v in guides.topics().items()]}
            elif method == "resources/read":
                from . import guides
                uri = str(params.get("uri", ""))
                try:
                    text = guides.read(uri[len(GUIDE_URI):] if uri.startswith(GUIDE_URI) else "?")
                except KeyError:
                    return {"jsonrpc": "2.0", "id": mid,
                            "error": {"code": -32602, "message": f"unknown resource {uri}"}}
                result = {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": text}]}
            elif method == "prompts/list":
                result = {"prompts": []}
            else:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}}
            return {"jsonrpc": "2.0", "id": mid, "result": result}
        except Exception as e:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    sys.stdout = sys.stderr            # stray prints must never corrupt the protocol stream
    lock = threading.Lock()

    def emit(msg: dict, alive=None) -> None:
        data = (json.dumps(msg, ensure_ascii=False, default=str) + "\n").encode("utf-8")
        with lock:                     # replies and progress notifications never interleave
            if alive is not None and not alive():
                return
            try:
                stdout.write(data)
                stdout.flush()
            except (OSError, ValueError):
                pass

    visible = "--hidden" not in argv and os.environ.get("INVENTOR_FORGE_VISIBLE", "1").strip() not in ("0", "false", "no")
    server = Server(visible=visible, emit=emit, lock=lock)
    try:
        for raw in stdin:
            raw = raw.strip()
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            batch = msg if isinstance(msg, list) else [msg]
            replies = [r for r in (server.handle(m) for m in batch) if r is not None]
            for rep in replies:
                emit(rep)
    finally:
        server.finish()                # the client closed the connection: tidy up what this session started



if __name__ == "__main__":
    main()
