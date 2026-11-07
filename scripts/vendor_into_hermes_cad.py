"""Copy the inventor_forge package into hermes-cad's Inventor backend (backends/inventor/forge).

    python scripts/vendor_into_hermes_cad.py ../cad-plugin
"""
import os
import shutil
import sys

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
target_root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "cad-plugin"))
src = os.path.join(here, "inventor_forge")
dst = os.path.join(target_root, "backends", "inventor", "forge")
if not os.path.isdir(os.path.join(target_root, "backends", "inventor")):
    raise SystemExit(f"not a hermes-cad checkout: {target_root}")
if os.path.isdir(dst):
    shutil.rmtree(dst)
shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "_constants_cache.json",
                                                        "server.py", "__main__.py"))
with open(os.path.join(src, "..", "LICENSE"), encoding="utf-8") as f:
    lic = f.read()
with open(os.path.join(dst, "LICENSE"), "w", encoding="utf-8") as f:
    f.write(lic)
print(f"vendored {src} -> {dst}")
