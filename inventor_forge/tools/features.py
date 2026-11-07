"""Solid features. Every geometry-changing tool returns a ``delta`` (volume / face / edge change)
so the caller can check the feature did what was intended."""
from __future__ import annotations

import math

from ..com import MM, InventorError, K, items, r, safe
from ..registry import tool
from ..session import Session
from .inspect import face_normal, find_planar_face

OPS = {"join": "kJoinOperation", "cut": "kCutOperation", "intersect": "kIntersectOperation",
       "new_body": "kNewBodyOperation"}
DIRS = {"positive": "kPositiveExtentDirection", "negative": "kNegativeExtentDirection",
        "symmetric": "kSymmetricExtentDirection"}


def _op(name: str) -> int:
    key = OPS.get(name.lower())
    if not key:
        raise InventorError(f"operation must be one of {sorted(OPS)}")
    return getattr(K, key)


def _dir(name: str) -> int:
    key = DIRS.get(name.lower())
    if not key:
        raise InventorError(f"direction must be one of {sorted(DIRS)} (or auto)")
    return getattr(K, key)


def _feature(s: Session, ref):
    """Feature by 1-based index (in the browser order) or by name."""
    feats = s.cdef().Features
    if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
        i = int(ref)
        if not 1 <= i <= feats.Count:
            raise InventorError(f"feature {i} out of range 1..{feats.Count} (see list_features)")
        return feats.Item(i)
    for f in items(feats):
        if f.Name.lower() == str(ref).lower():
            return f
    raise InventorError(f"no feature named {ref!r} (see list_features)")


def _try_directions(s: Session, label: str, make, first: str, second: str):
    """Build a feature in one direction; if it removed/added nothing, delete it and try the other."""
    before = s.snapshot()
    feat = None
    try:
        feat = make(first)
    except Exception:
        feat = None
    after = s.snapshot()
    if feat is not None and abs(after.volume - before.volume) > 1e-6:
        return feat, first, before
    if feat is not None:
        safe(lambda: feat.Delete(True, False, False))   # keep the sketch for the retry
    feat = make(second)
    return feat, second, before


def _profile(s: Session, sketch_index: int = 0):
    sk = s.sketch(sketch_index)
    try:
        return sk, sk.Profiles.AddForSolid()
    except Exception as e:
        raise InventorError(f"sketch {sk.Name} has no closed profile — close the outline "
                            f"(draw_closed_profile, draw_rectangle...)") from e


@tool("features")
def extrude(s: Session, distance: float = 10.0, operation: str = "join", direction: str = "auto",
            through_all: bool = False, taper: float = 0.0, sketch_index: int = 0) -> dict:
    """Extrude the active sketch's closed profile(s) — all closed regions, inner loops become holes.

    distance: mm (ignored with through_all)
    operation: join | cut | intersect | new_body
    direction: auto | positive | negative | symmetric. auto = positive for join, and for cut whichever
      side actually removes material
    through_all: cut/extrude through everything
    taper: draft angle in degrees (negative tapers inward)
    sketch_index: 1-based sketch, 0 = the active sketch
    """
    sk, prof = _profile(s, sketch_index)
    ef = s.cdef().Features.ExtrudeFeatures
    opv = _op(operation)

    def make(dirname: str):
        d = ef.CreateExtrudeDefinition(prof, opv)
        if through_all:
            d.SetThroughAllExtent(_dir("positive" if dirname == "symmetric" else dirname))
        else:
            if distance <= 0:
                raise InventorError("distance must be positive (use direction for the side)")
            d.SetDistanceExtent(distance * MM, _dir(dirname))
        if taper:
            d.TaperAngle = f"{taper} deg"
        return ef.Add(d)

    if direction == "auto":
        if operation == "cut":
            feat, used, before = _try_directions(s, "Extrude", make, "negative", "positive")
        else:
            before = s.snapshot()
            feat, used = make("positive"), "positive"
    else:
        before = s.snapshot()
        feat, used = make(direction), direction
    out = s.delta(feat.Name, before)
    out.update({"feature": feat.Name, "direction": used, "sketch": sk.Name})
    return out


@tool("features")
def revolve(s: Session, axis: str = "Y", angle: float = 360.0, operation: str = "join",
            sketch_index: int = 0) -> dict:
    """Revolve the active sketch's profile about an axis.

    axis: X | Y | Z (model work axes), a work axis name, or "sketch" = the first construction line
      in the sketch (draw it with draw_line(..., construction=true))
    angle: degrees (360 = full)
    """
    sk, prof = _profile(s, sketch_index)
    rf = s.cdef().Features.RevolveFeatures
    if axis.lower() == "sketch":
        lines = [l for l in items(sk.SketchLines) if l.Construction]
        if not lines:
            raise InventorError("no construction line in the sketch to revolve about")
        ax = lines[0]
    else:
        ax = s.work_axis(axis)
    before = s.snapshot()
    if abs(angle) >= 360:
        feat = rf.AddFull(prof, ax, _op(operation))
    else:
        feat = rf.AddByAngle(prof, ax, math.radians(abs(angle)),
                             _dir("positive" if angle > 0 else "negative"), _op(operation))
    out = s.delta(feat.Name, before)
    out["feature"] = feat.Name
    return out


def _hole_feature(s: Session, placement, dia_or_tap, depth, dirname, cbore, csink):
    hf = s.cdef().Features.HoleFeatures
    d = _dir(dirname)
    if depth and depth > 0:
        dep = depth * MM
        if cbore:
            return hf.AddCBoreByDistanceExtent(placement, dia_or_tap, dep, d, cbore[0] * MM, cbore[1] * MM)
        if csink:
            return hf.AddCSinkByDistanceExtent(placement, dia_or_tap, dep, d, csink[0] * MM, math.radians(csink[1]))
        return hf.AddDrilledByDistanceExtent(placement, dia_or_tap, dep, d)
    if cbore:
        return hf.AddCBoreByThroughAllExtent(placement, dia_or_tap, d, cbore[0] * MM, cbore[1] * MM)
    if csink:
        return hf.AddCSinkByThroughAllExtent(placement, dia_or_tap, d, csink[0] * MM, math.radians(csink[1]))
    return hf.AddDrilledByThroughAllExtent(placement, dia_or_tap, d)


@tool("features")
def hole(s: Session, x: float = 0.0, y: float = 0.0, diameter: float = 10.0, depth: float = 0.0,
         points: list[list[float]] | None = None, face_index: int = 0, axis: str = "Z",
         tap: str = "", tap_class: str = "6H", cbore_diameter: float = 0.0, cbore_depth: float = 0.0,
         csink_diameter: float = 0.0, csink_angle: float = 90.0, use_sketch_points: bool = False) -> dict:
    """Drilled, tapped, counterbored or countersunk hole(s), placed by model coordinates.

    x: mm, model X of the hole centre (y likewise); or give several centres in points
    points: [[x, y], ...] or [[x, y, z], ...] model coordinates (overrides x/y)
    depth: mm; 0 = through all
    face_index: planar face to drill from; 0 = the outermost face facing +axis
    axis: X | Y | Z — drilling axis used when face_index is 0 (holes go in from the + side)
    tap: thread designation, e.g. "M10x1.5" (ISO metric, class tap_class); diameter is then ignored
    cbore_diameter: counterbore Ø and cbore_depth (mm)
    csink_diameter: countersink Ø and csink_angle (degrees)
    use_sketch_points: drill every hole-centre point of the active sketch instead (draw_point)
    """
    cd = s.cdef()
    if use_sketch_points:
        sk = s.sketch()
        pts = [p for p in items(sk.SketchPoints) if p.HoleCenter]
        if not pts:
            raise InventorError("the active sketch has no hole-centre points")
    else:
        first = (points or [[x, y]])[0]
        face = s.face(face_index) if face_index else (find_planar_face(s, axis, at=first[:2]) or
                                                      find_planar_face(s, axis))
        if face is None:
            raise InventorError(f"no planar face facing +{axis}; pass face_index")
        sk = cd.Sketches.Add(face, False)
        n = face_normal(face)
        p0 = face.PointOnFace
        centres = points if points else [[x, y]]
        pts = []
        for c in centres:
            if len(c) >= 3:
                mp = s.p3(*c[:3])
            else:
                # put the 2-D coordinate on the face plane along the face normal
                ax = max(range(3), key=lambda i: abs(n[i]))
                full = [0.0, 0.0, 0.0]
                rest = [i for i in range(3) if i != ax]
                full[rest[0]], full[rest[1]] = c[0], c[1]
                full[ax] = [p0.X, p0.Y, p0.Z][ax] * 10
                mp = s.p3(*full)
            pts.append(sk.SketchPoints.Add(sk.ModelToSketchSpace(mp), True))
    placement = cd.Features.HoleFeatures.CreateSketchPlacementDefinition(s.collection(pts))
    if tap:
        dia_or_tap = cd.Features.HoleFeatures.CreateTapInfo(True, "ISO Metric profile", tap, tap_class, True)
    else:
        if diameter <= 0:
            raise InventorError("diameter must be positive")
        dia_or_tap = diameter * MM
    cbore = (cbore_diameter, cbore_depth) if cbore_diameter else None
    csink = (csink_diameter, csink_angle) if csink_diameter else None

    feat, used, before = _try_directions(
        s, "Hole", lambda dn: _hole_feature(s, placement, dia_or_tap, depth, dn, cbore, csink),
        "positive", "negative")
    out = s.delta(feat.Name, before)
    out.update({"feature": feat.Name, "holes": len(pts), "kind": "tapped " + tap if tap else
                ("counterbored" if cbore else "countersunk" if csink else "drilled"),
                "through": not depth})
    return out


@tool("features")
def hole_linear(s: Session, face_index: int, edge_one: int, distance_one: float, edge_two: int,
                distance_two: float, diameter: float = 10.0, depth: float = 0.0, tap: str = "") -> dict:
    """Hole on a planar face positioned by distances from two of its edges (Inventor's linear placement).

    distance_one: mm from edge_one (edge indices from list_edges)
    """
    cd = s.cdef()
    face = s.face(face_index)
    hf = cd.Features.HoleFeatures
    bias = face.PointOnFace
    placement = hf.CreateLinearPlacementDefinition(face, s.edge(edge_one), distance_one * MM,
                                                   s.edge(edge_two), distance_two * MM, bias)
    dia = hf.CreateTapInfo(True, "ISO Metric profile", tap, "6H", True) if tap else diameter * MM
    feat, used, before = _try_directions(
        s, "Hole", lambda dn: _hole_feature(s, placement, dia, depth, dn, None, None), "positive", "negative")
    out = s.delta(feat.Name, before)
    out["feature"] = feat.Name
    return out


@tool("features")
def fillet(s: Session, radius: float, edges: list[int]) -> dict:
    """Constant-radius fillet on edges (1-based indices from list_edges / find_edge)."""
    before = s.snapshot()
    ec = s.edge_collection([s.edge(i) for i in edges])
    feat = s.cdef().Features.FilletFeatures.AddSimple(ec, radius * MM)
    out = s.delta(feat.Name, before)
    out["feature"] = feat.Name
    return out


@tool("features")
def chamfer(s: Session, distance: float, edges: list[int], distance_two: float = 0.0, angle: float = 0.0,
            face_index: int = 0) -> dict:
    """Chamfer edges: equal distance, two distances, or distance + angle (needs face_index for the
    reference face of the last two forms)."""
    before = s.snapshot()
    cf = s.cdef().Features.ChamferFeatures
    ec = s.edge_collection([s.edge(i) for i in edges])
    if distance_two:
        feat = cf.AddUsingTwoDistances(ec, s.face(face_index), distance * MM, distance_two * MM)
    elif angle:
        feat = cf.AddUsingDistanceAndAngle(ec, s.face(face_index), distance * MM, math.radians(angle))
    else:
        feat = cf.AddUsingDistance(ec, distance * MM)
    out = s.delta(feat.Name, before)
    out["feature"] = feat.Name
    return out


@tool("features")
def circular_pattern(s: Session, features: list[str], count: int = 6, angle: float = 360.0,
                     axis: str = "Z") -> dict:
    """Circular pattern of features (names or 1-based indices) about an axis (X/Y/Z or work axis name)."""
    before = s.snapshot()
    parents = s.collection([_feature(s, f) for f in features])
    feat = s.cdef().Features.CircularPatternFeatures.Add(parents, s.work_axis(axis), True, int(count),
                                                         f"{angle} deg", True)
    out = s.delta(feat.Name, before)
    out["feature"] = feat.Name
    return out


@tool("features")
def rectangular_pattern(s: Session, features: list[str], x_count: int = 2, x_spacing: float = 20.0,
                        y_count: int = 1, y_spacing: float = 20.0, x_axis: str = "X", y_axis: str = "Y") -> dict:
    """Rectangular (grid) pattern of features along two axes; spacing in mm (negative flips the direction)."""
    before = s.snapshot()
    parents = s.collection([_feature(s, f) for f in features])
    rp = s.cdef().Features.RectangularPatternFeatures
    if y_count > 1:
        feat = rp.Add(parents, s.work_axis(x_axis), x_spacing >= 0, int(x_count), abs(x_spacing) * MM,
                      YDirectionEntity=s.work_axis(y_axis), NaturalYDirection=y_spacing >= 0,
                      YCount=int(y_count), YSpacing=abs(y_spacing) * MM)
    else:
        feat = rp.Add(parents, s.work_axis(x_axis), x_spacing >= 0, int(x_count), abs(x_spacing) * MM)
    out = s.delta(feat.Name, before)
    out["feature"] = feat.Name
    return out


@tool("features")
def mirror(s: Session, features: list[str], plane: str = "YZ") -> dict:
    """Mirror features (names / indices) across a plane (XY, XZ, YZ or work plane name)."""
    before = s.snapshot()
    parents = s.collection([_feature(s, f) for f in features])
    feat = s.cdef().Features.MirrorFeatures.Add(parents, s.work_plane(plane))
    out = s.delta(feat.Name, before)
    out["feature"] = feat.Name
    return out


@tool("features")
def shell(s: Session, thickness: float, remove_faces: list[int] | None = None, direction: str = "inside") -> dict:
    """Hollow the body to a wall thickness, leaving the listed faces open.

    direction: inside | outside | both
    """
    before = s.snapshot()
    sf = s.cdef().Features.ShellFeatures
    faces = s.face_collection([s.face(i) for i in (remove_faces or [])])
    dmap = {"inside": "kInsideShellDirection", "outside": "kOutsideShellDirection", "both": "kBothSidesShellDirection"}
    d = sf.CreateShellDefinition(faces, thickness * MM, getattr(K, dmap.get(direction, "kInsideShellDirection")))
    feat = sf.Add(d)
    out = s.delta(feat.Name, before)
    out["feature"] = feat.Name
    return out


@tool("features")
def thread(s: Session, face_index: int, designation: str = "M10x1.5", internal: bool = False,
           thread_class: str = "", length: float = 0.0) -> dict:
    """Cosmetic (modelled-as-annotation) ISO metric thread on a cylindrical face — shows on drawings
    and in the BOM without heavy helical geometry.

    designation: e.g. M10x1.5, M8x1.25
    length: mm; 0 = full length
    """
    tf = s.cdef().Features.ThreadFeatures
    face = s.face(face_index)
    if face.SurfaceType != K.kCylinderSurface:
        raise InventorError(f"face {face_index} is not cylindrical")
    cls = thread_class or ("6H" if internal else "6g")
    info = tf.CreateStandardThreadInfo(internal, True, "ISO Metric profile", designation, cls)
    start = face.Edges.Item(1)
    before = s.snapshot()
    if length:
        feat = tf.Add(face, start, info, False, False, length * MM, 0)
    else:
        feat = tf.Add(face, start, info, False, True)
    out = s.delta(feat.Name, before)
    out["feature"] = feat.Name
    return out


@tool("features")
def sweep(s: Session, profile_sketch: int, path_sketch: int, operation: str = "join") -> dict:
    """Sweep a closed profile (sketch index) along a path (first curve chain of another sketch)."""
    cd = s.cdef()
    _, prof = _profile(s, profile_sketch)
    psk = s.sketch(path_sketch)
    ents = [e for e in items(psk.SketchEntities) if safe(lambda e=e: e.Type != K.kSketchPointObject, False)]
    if not ents:
        raise InventorError("path sketch has no curves")
    path = cd.Features.SweepFeatures.CreatePath(ents[0])
    before = s.snapshot()
    feat = cd.Features.SweepFeatures.AddUsingPath(prof, path, _op(operation))
    out = s.delta(feat.Name, before)
    out["feature"] = feat.Name
    return out


@tool("features")
def loft(s: Session, sketches: list[int], operation: str = "join") -> dict:
    """Loft through the closed profiles of two or more sketches (1-based indices, in order)."""
    cd = s.cdef()
    secs = s.collection([s.sketch(i).Profiles.AddForSolid() for i in sketches])
    lf = cd.Features.LoftFeatures
    before = s.snapshot()
    feat = lf.Add(lf.CreateLoftDefinition(secs, _op(operation)))
    out = s.delta(feat.Name, before)
    out["feature"] = feat.Name
    return out


@tool("features")
def work_plane(s: Session, base: str = "XY", offset: float = 0.0, angle: float = 0.0, axis: str = "",
               name: str = "") -> dict:
    """Work plane offset from a base plane (mm), or rotated about an axis by an angle (degrees).

    base: XY | XZ | YZ | existing work plane name
    axis: X | Y | Z — required for angle planes
    name: optional name to refer to it later (create_sketch(plane=name), mirror(plane=name))
    """
    wps = s.cdef().WorkPlanes
    if angle:
        if not axis:
            raise InventorError("an angled work plane needs an axis")
        wp = wps.AddByLinePlaneAndAngle(s.work_axis(axis), s.work_plane(base), math.radians(angle))
    else:
        wp = wps.AddByPlaneAndOffset(s.work_plane(base), offset * MM)
    if name:
        wp.Name = name
    return {"work_plane": wp.Name}


@tool("features")
def work_axis(s: Session, face_index: int = 0, edge_index: int = 0, name: str = "") -> dict:
    """Work axis through a cylindrical face's axis or along a straight edge (for patterns/revolves)."""
    was = s.cdef().WorkAxes
    if face_index:
        wa = was.AddByRevolvedFace(s.face(face_index))
    elif edge_index:
        wa = was.AddByLine(s.edge(edge_index))
    else:
        raise InventorError("give face_index (cylindrical face) or edge_index")
    if name:
        wa.Name = name
    return {"work_axis": wa.Name}


@tool("features", mutates=False)
def list_features(s: Session) -> dict:
    """Feature tree: index, name, type, suppressed, health."""
    out = []
    for i, f in enumerate(items(s.cdef().Features), 1):
        out.append({"index": i, "name": f.Name, "type": K.name_of(f.Type, "k").replace("k", "", 1).replace("Object", ""),
                    "suppressed": bool(safe(lambda f=f: f.Suppressed, False)),
                    "health": K.name_of(safe(lambda f=f: f.HealthStatus, 0), "k").replace("HealthStatus", "")})
    return {"features": out, "count": len(out)}


@tool("features")
def delete_feature(s: Session, features: list[str], keep_sketches: bool = False) -> dict:
    """Delete features by name or 1-based index (dependent features go too)."""
    before = s.snapshot()
    targets = [_feature(s, f) for f in features]
    names = [t.Name for t in targets]
    for t in targets:
        t.Delete(bool(keep_sketches), False, False)
    out = s.delta("Delete " + ", ".join(names), before)
    out["deleted"] = names
    return out


@tool("features")
def suppress_feature(s: Session, feature: str, suppress: bool = True) -> dict:
    """Suppress (or unsuppress) a feature without deleting it — handy for what-if checks."""
    before = s.snapshot()
    f = _feature(s, feature)
    f.Suppressed = bool(suppress)
    s.part().Update()
    out = s.delta(("Suppress " if suppress else "Unsuppress ") + f.Name, before)
    return out
