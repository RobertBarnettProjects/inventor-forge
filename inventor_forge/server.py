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
import traceback

from . import __version__
from .com import InventorError
from .engine import Forge

PROTOCOL = "2025-06-18"
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
    "session: drawings, fastener and material choices follow it. execute_python is the escape hatch."
)


class Server:
    def __init__(self, visible: bool = True):
        self.forge = Forge(visible=visible)

    def tools_list(self) -> list[dict]:
        out = []
        for t in self.forge.tools.values():
            out.append({"name": t.name, "description": t.description, "inputSchema": t.schema,
                        "annotations": {"readOnlyHint": not t.mutates}})
        return out

    def tools_call(self, name: str, args: dict) -> dict:
        try:
            res = self.forge.call(name, args)
            content = [{"type": "text", "text": json.dumps(res, ensure_ascii=False, default=str)}]
            if name in IMAGE_TOOLS and res.get("path", "").lower().endswith(".png") and os.path.exists(res["path"]):
                if os.path.getsize(res["path"]) < 4_000_000:
                    with open(res["path"], "rb") as f:
                        content.append({"type": "image", "mimeType": "image/png",
                                        "data": base64.b64encode(f.read()).decode()})
            return {"content": content, "isError": False}
        except InventorError as e:
            return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
        except Exception as e:  # noqa: BLE001
            tb = traceback.format_exc(limit=5)[-1500:]
            return {"content": [{"type": "text", "text": f"Error: {type(e).__name__}: {e}\n{tb}"}], "isError": True}

    def handle(self, msg: dict) -> dict | None:
        mid = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params") or {}
        if mid is None:          # notification
            return None
        try:
            if method == "initialize":
                result = {"protocolVersion": params.get("protocolVersion", PROTOCOL),
                          "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": "inventor-forge", "version": __version__},
                          "instructions": INSTRUCTIONS}
            elif method == "tools/list":
                result = {"tools": self.tools_list()}
            elif method == "tools/call":
                result = self.tools_call(params.get("name", ""), params.get("arguments") or {})
            elif method == "ping":
                result = {}
            elif method in ("resources/list", "prompts/list"):
                result = {method.split("/")[0]: []}
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
    server = Server(visible="--hidden" not in argv)
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
            stdout.write((json.dumps(rep, ensure_ascii=False, default=str) + "\n").encode("utf-8"))
            stdout.flush()


if __name__ == "__main__":
    main()
