"""Sketches: planes / offsets / faces, and dimensioned geometry (so it stays parametric)."""
from __future__ import annotations

import math

from ..com import MM, InventorError, K, items, r, safe
from ..registry import tool
from ..session import Session


def _axes(sk) -> dict:
    """Where the sketch's x / y axes point in model space (so callers can place geometry)."""
    tg = sk.Application.TransientGeometry
    o = sk.SketchToModelSpace(tg.CreatePoint2d(0, 0))
    x = sk.SketchToModelSpace(tg.CreatePoint2d(1, 0))
    y = sk.SketchToModelSpace(tg.CreatePoint2d(0, 1))
    vec = lambda p: [r(p.X - o.X, 4), r(p.Y - o.Y, 4), r(p.Z - o.Z, 4)]
    out = {"origin_mm": [r(o.X * 10), r(o.Y * 10), r(o.Z * 10)], "sketch_x_dir": vec(x), "sketch_y_dir": vec(y)}
    names = []
    for key in ("sketch_x_dir", "sketch_y_dir"):
        v = out[key]
        i = max(range(3), key=lambda k: abs(v[k]))
        names.append(("-" if v[i] < 0 else "+") + "XYZ"[i] if abs(v[i]) > 0.999 else "oblique")
    out["mapping"] = f"sketch x → model {names[0]}, sketch y → model {names[1]}"
    if any(n.startswith("-") for n in names):
        out["mapping"] += " (note the minus: a model coordinate c on that axis is drawn at sketch −c)"
    return out


def _sketch_info(sk) -> dict:
    return {"sketch": sk.Name, "entities": safe(lambda: sk.SketchEntities.Count, 0),
            "dimensions": safe(lambda: sk.DimensionConstraints.Count, 0)}


@tool("sketch")
def create_sketch(s: Session, plane: str = "XY", offset: float = 0.0, face_index: int = 0) -> dict:
    """Start a new sketch on a base plane (XY, XZ, YZ or a work plane name), optionally offset along
    its normal, or on a planar face of the body. Later draw_* calls go into this sketch.

    plane: XY | XZ | YZ | work plane name (ignored when face_index is given)
    offset: mm, creates an offset work plane first
    face_index: 1-based planar face (see list_faces / find_face); 0 = use plane
    """
    cd = s.cdef()
    if face_index:
        f = s.face(face_index)
        if f.SurfaceType != K.kPlaneSurface:
            raise InventorError(f"face {face_index} is not planar")
        target = f
    else:
        target = s.work_plane(plane)
        if offset:
            target = cd.WorkPlanes.AddByPlaneAndOffset(target, offset * MM, False)
            target.Visible = False
    sk = cd.Sketches.Add(target, False)
    s.set_sketch(sk)
    out = {**_sketch_info(sk), "on": f"face {face_index}" if face_index else plane + (f" + {offset} mm" if offset else "")}
    out.update(_axes(sk))
    return out


@tool("sketch")
def select_sketch(s: Session, index: int = 0, name: str = "") -> dict:
    """Make an existing sketch the target of draw_* / extrude (by 1-based index or name)."""
    cd = s.cdef()
    if name:
        for sk in items(cd.Sketches):
            if sk.Name.lower() == name.lower():
                s.set_sketch(sk)
                return _sketch_info(sk)
        raise InventorError(f"no sketch named {name!r}")
    sk = s.sketch(index or cd.Sketches.Count)
    s.set_sketch(sk)
    return {**_sketch_info(sk), **_axes(sk)}


def _dim(sk, kind: str, *ents, at=(0.0, 0.0)):
    """Add a driving dimension; failures (over-constraint) are tolerated — geometry still exists."""
    tg = sk.Application.TransientGeometry
    tp = tg.CreatePoint2d(at[0] * MM, at[1] * MM)
    dc = sk.DimensionConstraints
    try:
        if kind == "h":
            return dc.AddTwoPointDistance(ents[0], ents[1], K.kHorizontalDim, tp)
        if kind == "v":
            return dc.AddTwoPointDistance(ents[0], ents[1], K.kVerticalDim, tp)
        if kind == "a":
            return dc.AddTwoPointDistance(ents[0], ents[1], K.kAlignedDim, tp)
        if kind == "d":
            return dc.AddDiameter(ents[0], tp)
        if kind == "r":
            return dc.AddRadius(ents[0], tp)
    except Exception:
        return None


@tool("sketch")
def draw_rectangle(s: Session, width: float, height: float, x: float = 0.0, y: float = 0.0,
                   centered: bool = True, dimension: bool = True) -> dict:
    """Rectangle in the active sketch, width along sketch x, height along sketch y.

    x: mm, centre (or lower-left corner when centered=false)
    centered: (x, y) is the centre; false = (x, y) is the lower-left corner
    dimension: add width/height dimensions (editable later with edit_dimension)
    """
    sk = s.sketch()
    if width <= 0 or height <= 0:
        raise InventorError("width and height must be positive")
    if centered:
        lines = sk.SketchLines.AddAsTwoPointCenteredRectangle(s.p2(x, y), s.p2(x + width / 2, y + height / 2))
        cx, cy = x, y
    else:
        lines = sk.SketchLines.AddAsTwoPointRectangle(s.p2(x, y), s.p2(x + width, y + height))
        cx, cy = x + width / 2, y + height / 2
    segs = [lines.Item(i) for i in range(1, lines.Count + 1)]
    dims = []
    if dimension:
        horiz = [l for l in segs if abs(l.Geometry.Direction.Y) < 1e-9]
        vert = [l for l in segs if abs(l.Geometry.Direction.X) < 1e-9]
        if horiz:
            l = horiz[0]
            d = _dim(sk, "h", l.StartSketchPoint, l.EndSketchPoint, at=(cx, cy - height / 2 - 8))
            dims.append(d.Parameter.Name if d is not None else None)
        if vert:
            l = vert[0]
            d = _dim(sk, "v", l.StartSketchPoint, l.EndSketchPoint, at=(cx - width / 2 - 8, cy))
            dims.append(d.Parameter.Name if d is not None else None)
    return {**_sketch_info(sk), "drew": f"rectangle {width}×{height} mm", "dimension_parameters": [d for d in dims if d]}


@tool("sketch")
def draw_circle(s: Session, diameter: float, x: float = 0.0, y: float = 0.0, construction: bool = False,
                dimension: bool = True) -> dict:
    """Circle in the active sketch (diameter dimension added).

    x: mm, centre in sketch coordinates
    """
    sk = s.sketch()
    if diameter <= 0:
        raise InventorError("diameter must be positive")
    c = sk.SketchCircles.AddByCenterRadius(s.p2(x, y), diameter / 2 * MM)
    if construction:
        c.Construction = True
    d = _dim(sk, "d", c, at=(x + diameter * 0.6, y + diameter * 0.6)) if dimension else None
    return {**_sketch_info(sk), "drew": f"circle Ø{diameter} at ({x}, {y})",
            "dimension_parameter": d.Parameter.Name if d is not None else None}


@tool("sketch")
def draw_line(s: Session, x1: float, y1: float, x2: float, y2: float, construction: bool = False) -> dict:
    """Line from (x1, y1) to (x2, y2) mm in the active sketch (construction lines don't make profiles,
    but can be revolve axes)."""
    sk = s.sketch()
    ln = sk.SketchLines.AddByTwoPoints(s.p2(x1, y1), s.p2(x2, y2))
    if construction:
        ln.Construction = True
    return {**_sketch_info(sk), "drew": "line", "length_mm": r(math.hypot(x2 - x1, y2 - y1))}


@tool("sketch")
def draw_arc(s: Session, x: float, y: float, radius: float, start_angle: float = 0.0,
             sweep_angle: float = 180.0) -> dict:
    """Arc by centre, radius (mm), start angle and sweep (degrees, counter-clockwise)."""
    sk = s.sketch()
    sk.SketchArcs.AddByCenterStartSweepAngle(s.p2(x, y), radius * MM, math.radians(start_angle),
                                             math.radians(sweep_angle))
    return {**_sketch_info(sk), "drew": f"arc R{radius}"}


@tool("sketch")
def draw_polygon(s: Session, sides: int = 6, radius: float = 10.0, x: float = 0.0, y: float = 0.0,
                 inscribed: bool = True) -> dict:
    """Regular polygon. inscribed=true: radius to the corners; false: radius to the flats
    (a hex nut across flats S uses radius=S/2, inscribed=false)."""
    sk = s.sketch()
    if sides < 3:
        raise InventorError("a polygon needs at least 3 sides")
    sk.SketchLines.AddAsPolygon(int(sides), s.p2(x, y), s.p2(x + radius, y), bool(inscribed))
    across_flats = 2 * radius * (math.cos(math.pi / sides) if inscribed else 1)
    return {**_sketch_info(sk), "drew": f"{sides}-gon", "across_flats_mm": r(across_flats)}


@tool("sketch")
def draw_closed_profile(s: Session, points: list[list[float]], close: bool = True) -> dict:
    """Connected polyline through [[x, y], ...] mm (closed back to the first point by default).
    Segments share endpoints, so the result is one clean profile."""
    sk = s.sketch()
    pts = [tuple(map(float, p[:2])) for p in points]
    if len(pts) < 2:
        raise InventorError("need at least 2 points")
    if close and pts[0] == pts[-1]:
        pts = pts[:-1]
    first = prev = None
    lines = sk.SketchLines
    for i in range(1, len(pts)):
        start = prev.EndSketchPoint if prev is not None else s.p2(*pts[0])
        ln = lines.AddByTwoPoints(start, s.p2(*pts[i]))
        first = first or ln
        prev = ln
    if close and len(pts) >= 3:
        lines.AddByTwoPoints(prev.EndSketchPoint, first.StartSketchPoint)
    return {**_sketch_info(sk), "drew": f"{'closed ' if close else ''}polyline, {len(pts)} points"}


@tool("sketch")
def draw_slot(s: Session, length: float, width: float, x: float = 0.0, y: float = 0.0, angle: float = 0.0) -> dict:
    """Straight slot (obround): centre-to-centre length, width, centre (x, y), angle in degrees."""
    sk = s.sketch()
    a = math.radians(angle)
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    h, w = length / 2, width / 2
    c1 = (x - ux * h, y - uy * h)
    c2 = (x + ux * h, y + uy * h)
    p = lambda c, sgn: s.p2(c[0] + sgn * nx * w, c[1] + sgn * ny * w)
    l1 = sk.SketchLines.AddByTwoPoints(p(c1, 1), p(c2, 1))
    l2 = sk.SketchLines.AddByTwoPoints(p(c2, -1), p(c1, -1))
    arcs = sk.SketchArcs
    arcs.AddByCenterStartEndPoint(s.p2(*c2), l2.StartSketchPoint, l1.EndSketchPoint, True)
    arcs.AddByCenterStartEndPoint(s.p2(*c1), l1.StartSketchPoint, l2.EndSketchPoint, True)
    return {**_sketch_info(sk), "drew": f"slot {length}+{width} × {width}"}


@tool("sketch")
def draw_point(s: Session, x: float, y: float, hole_center: bool = True) -> dict:
    """Sketch point (a hole centre by default — hole(..., use_sketch_points=true) drills them all)."""
    sk = s.sketch()
    sk.SketchPoints.Add(s.p2(x, y), bool(hole_center))
    return {**_sketch_info(sk), "drew": f"point ({x}, {y})"}


@tool("sketch", mutates=False)
def sketch_info(s: Session, index: int = 0) -> dict:
    """Entities, dimensions, profile count and constraint status of the active (or given) sketch."""
    sk = s.sketch(index)
    out = _sketch_info(sk)
    out.update(_axes(sk))
    out["dimension_list"] = [{"parameter": d.Parameter.Name, "value_mm_or_deg": r(d.Parameter.ModelValue * (10 if
                              "Angle" not in safe(lambda: d.Parameter.Units, "") else 57.29578)),
                              "expression": d.Parameter.Expression} for d in items(sk.DimensionConstraints)]
    out["constraint_status"] = safe(lambda: K.name_of(sk.ConstraintStatus, "k"), "?")
    out["closed_profiles"] = safe(lambda: sk.Profiles.AddForSolid().Count, 0)
    return out
