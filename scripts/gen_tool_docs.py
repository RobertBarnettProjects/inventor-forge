"""Regenerate TOOLS.md from the tool registry: python scripts/gen_tool_docs.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inventor_forge.registry import load_all  # noqa: E402

ORDER = ["session", "documents", "view", "sketch", "features", "inspect", "parameters", "properties", "materials",
         "sheet_metal", "assembly", "drawing", "analysis", "system"]
tools = load_all()
lines = ["# inventor-forge tools", "", f"{len(tools)} tools. Lengths mm, angles degrees, forces N, stresses MPa.", ""]
for g in ORDER + sorted({t.group for t in tools.values()} - set(ORDER)):
    group = [t for t in tools.values() if t.group == g]
    if not group:
        continue
    lines += [f"## {g.replace('_', ' ').title()}", "", "| Tool | What it does | Arguments |", "|---|---|---|"]
    for t in group:
        args = ", ".join(f"`{k}`" + ("*" if k in t.schema.get("required", []) else "") for k in t.schema["properties"])
        lines.append(f"| `{t.name}` | {t.description.replace('|', '/')} | {args} |")
    lines.append("")
lines.append("`*` = required.")
out = os.path.join(os.path.dirname(__file__), "..", "TOOLS.md")
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("wrote", os.path.abspath(out), len(tools), "tools")
