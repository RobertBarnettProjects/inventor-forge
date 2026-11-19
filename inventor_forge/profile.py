"""What each tool does beyond its schema, for clients that build on this server (published in each tool's MCP
``_meta`` under ``cad/*`` keys, and once for the whole server in ``initialize``).

A client such as an agent plugin needs to know more than a tool's arguments before it calls it:

- ``cad/geometry``: the tool changes the model's shape, so a 3D preview should be refreshed afterwards.
- ``cad/takes_input``: the tool takes over the user's mouse and keyboard while it runs, so the user must be told
  first. ``true``, or ``{"if_args": {...}}`` when only some argument values do.
- ``cad/runs_code``: the tool runs code it is given (an approval with the code shown is due).
- ``cad/files``: which arguments name files the tool ``writes`` or ``reads``, and which only become part of a file
  ``names`` (to be reduced to a plain name). A client that sandboxes writes needs no guessing from argument names.
- ``cad/budget``: how long to wait before giving up on the call: ``floor_s`` always; a tool with its own time limit
  argument (``timeout_arg``) gets that limit, once per item of each ``repeat_args`` list (or the given default count
  when the list is left out), plus ``per_item_s`` around each and ``extra_s`` once.
- ``cad/progress``: the server sends MCP progress notifications while this tool runs, when the call carries a
  progress token (every tool does here, at least every ``PROGRESS_EVERY`` seconds).

No imports from the rest of the package except the registry, so this can be read without Inventor or pywin32.
"""
from __future__ import annotations

import inspect

PROFILE_VERSION = 1
PROGRESS_EVERY = 10.0           # s between progress notifications during a call
FLOOR_S = 1800.0                # s a call may hold the COM thread unless the tool says otherwise (engine.DEFAULT_WAIT)
PER_ITEM_S = 600.0
EXTRA_S_DEFAULT = 300.0
REPEAT_ARGS = {"cases": None, "fractions": 3}   # list arguments that repeat a tool's own time limit (default count)

# tools that change the model's shape (a preview of the model is out of date after them)
GEOMETRY = {
    "create_part", "create_assembly", "open_document", "activate_document", "undo", "delete_feature",
    "suppress_feature", "extrude", "revolve", "hole", "hole_linear", "fillet", "chamfer", "circular_pattern",
    "rectangular_pattern", "mirror", "shell", "sweep", "loft", "coil", "face_draft", "thicken_face", "split_part",
    "combine_bodies", "emboss_text", "set_parameter", "edit_dimension", "create_standard_part",
    "parametric_extrusion", "split_faces", "link_parameters", "activate_model_state", "set_component_model_state",
    "sheet_metal_face", "flange", "sheet_metal_cut", "set_sheet_metal_thickness", "place_component",
    "add_constraint", "move_component", "pattern_component", "frame_members", "tube_frame", "create_material",
    "set_appearance", "repair_import", "batch", "pose_bodies", "copy_assembly", "weld_body",
}

# tools that delete something that can't be brought back when an argument says so (the client asks the user first)
DELETES: dict[str, object] = {
    "purge_studies": {"if_args": {"confirm": True}},
    "clean_analysis_scratch": {"if_args": {"confirm": True}},
    "delete_study_item": True,
}

# tools whose own time limit covers only part of the call (a solve inside a longer set-up): extra seconds on top
EXTRA_S = {"analyze_stress": 1800.0, "analyze_modes": 1800.0, "mesh_convergence": 900.0}
SOLVE_S = {"analyze_stress": 3600.0, "analyze_modes": 3600.0}   # solves inside tools that take no timeout

# tools that drive Inventor's windows with the mouse and keyboard (Stress Analysis has no API for these steps)
TAKES_INPUT: dict[str, object] = {
    "analyze_stress": True,
    "analyze_modes": True,
    "result_at_point": True,
    "study_report": {"if_args": {"only_this_study": True}},
}

RUNS_CODE = {"execute_python"}


def _budget(fn) -> dict:
    sig = inspect.signature(fn).parameters
    name = fn.__name__
    b: dict = {"floor_s": FLOOR_S}
    if "timeout" in sig and sig["timeout"].default is not inspect.Parameter.empty:
        b.update(timeout_arg="timeout", timeout_default=sig["timeout"].default, per_item_s=PER_ITEM_S,
                 extra_s=EXTRA_S_DEFAULT + EXTRA_S.get(name, 0.0),
                 repeat_args={k: v for k, v in REPEAT_ARGS.items() if k in sig})
    elif name in SOLVE_S:
        b["floor_s"] = FLOOR_S + SOLVE_S[name] + EXTRA_S.get(name, 0.0)
    return b


def budget_for(meta: dict, args: dict) -> float:
    """The wait a ``cad/budget`` entry gives for these arguments (the same rule a client applies)."""
    floor = float(meta.get("floor_s") or FLOOR_S)
    arg = meta.get("timeout_arg")
    if not arg:
        return floor
    try:
        own = float(args.get(arg, meta.get("timeout_default")))
    except (TypeError, ValueError):
        return floor
    n = 1
    for name, fallback in (meta.get("repeat_args") or {}).items():
        v = args.get(name)
        # an empty or missing list means the tool's own default count
        n = max(n, len(v) if isinstance(v, (list, tuple)) and v else int(fallback or 1))
    return max(floor, n * (own + float(meta.get("per_item_s", PER_ITEM_S)))
               + float(meta.get("extra_s", EXTRA_S_DEFAULT)))


def tool_meta(t) -> dict:
    """The ``_meta`` entry of one registered tool."""
    from .fileargs import NAMES, READS, WRITES
    meta: dict = {"cad/budget": _budget(t.fn), "cad/progress": True}
    files = {k: list(v[t.name]) for k, v in (("writes", WRITES), ("reads", READS), ("names", NAMES)) if t.name in v}
    if files:
        meta["cad/files"] = files
        meta["inventor-forge/files"] = files          # the key earlier clients read
    if t.name in GEOMETRY:
        meta["cad/geometry"] = True
    if t.name in TAKES_INPUT:
        meta["cad/takes_input"] = TAKES_INPUT[t.name]
    if t.name in RUNS_CODE:
        meta["cad/runs_code"] = True
    if t.name in DELETES:
        meta["cad/deletes"] = DELETES[t.name]
    return meta


def server_profile() -> dict:
    """Sent once in ``initialize`` (``capabilities.experimental["cad/profile"]``)."""
    return {"version": PROFILE_VERSION, "family": "inventor", "units": {"length": "mm", "angle": "deg",
            "force": "N", "stress": "MPa"}, "preview_export": "STEP", "progress_every_s": PROGRESS_EVERY}
