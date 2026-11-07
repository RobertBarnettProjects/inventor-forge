"""Drawings (IDW): sheets, views, dimensions, annotations, parts lists, one-shot sheets, QA, PDF.

Sheet coordinates are millimetres from the sheet's lower-left corner. AS 1100 (default) uses
third-angle projection; ISO uses first-angle.
"""
from __future__ import annotations

import math
import os
import time

from ..com import MM, InventorError, K, items, r, safe
from ..registry import tool
from ..session import Session

SIZES = {"A0": "kA0DrawingSheetSize", "A1": "kA1DrawingSheetSize", "A2": "kA2DrawingSheetSize",
         "A3": "kA3DrawingSheetSize", "A4": "kA4DrawingSheetSize"}
ORIENT = {"front": "kFrontViewOrientation", "top": "kTopViewOrientation", "right": "kRightViewOrientation",
          "left": "kLeftViewOrientation", "back": "kBackViewOrientation", "bottom": "kBottomViewOrientation",
          "iso": "kIsoTopRightViewOrientation", "iso_left": "kIsoTopLeftViewOrientation"}
STYLES = {"hidden": "kHiddenLineDrawingViewStyle", "visible": "kHiddenLineRemovedDrawingViewStyle",
          "shaded": "kShadedDrawingViewStyle", "shaded_hidden": "kShadedHiddenLineDrawingViewStyle"}
STANDARD_SCALES = [10, 5, 4, 2.5, 2, 1, 1 / 2, 1 / 2.5, 1 / 4, 1 / 5, 1 / 10, 1 / 20, 1 / 25, 1 / 50, 1 / 100]
PDF_TRANSLATOR = "{0AC6FD96-2F4D-42CE-8BE0-8AEA580399E4}"


def _sheet(s: Session):
    return s.drawing().ActiveSheet


def _view(s: Session, name: str):
    sh = _sheet(s)
    vs = sh.DrawingViews
    if str(name).isdigit():
        i = int(name)
        if not 1 <= i <= vs.Count:
            raise InventorError(f"view {i} out of range 1..{vs.Count}")
        return vs.Item(i)
    for v in items(vs):
        if v.Name.lower() == str(name).lower() or safe(lambda v=v: v.Label.Text, "").lower().startswith(str(name).lower()):
            return v
    raise InventorError(f"no view {name!r} on sheet {sh.Name} (see list_views)")


def _scale_text(sc: float) -> str:
    if sc >= 1:
        return f"{sc:g}:1"
    return f"1:{1 / sc:g}"


def _box(v) -> tuple[float, float, float, float]:
    """(left, bottom, right, top) of a view in sheet mm."""
    left, top = v.Left * 10, v.Top * 10
    return left, top - v.Height * 10, left + v.Width * 10, top


def _lbox(v) -> tuple[float, float, float, float]:
    """View box including its label (drawn about 12 mm above the view when shown)."""
    b = _box(v)
    if not safe(lambda: v.ShowLabel, False):
        return b
    rb = safe(lambda: v.Label.RangeBox)
    if rb is None:
        return b[0], b[1], b[2], b[3] + 12.0
    return (min(b[0], rb.MinPoint.X * 10), min(b[1], rb.MinPoint.Y * 10),
            max(b[2], rb.MaxPoint.X * 10), max(b[3], rb.MaxPoint.Y * 10))

def _view_row(v) -> dict:
    b = _box(v)
    return {"name": v.Name, "scale": _scale_text(v.Scale), "center_mm": [r(v.Position.X * 10, 1), r(v.Position.Y * 10, 1)],
            "box_mm": [r(x, 1) for x in b], "size_mm": [r(b[2] - b[0], 1), r(b[3] - b[1], 1)],
            "type": K.name_of(safe(lambda: v.ViewType, 0), "k").replace("k", "", 1).replace("DrawingViewType", ""),
            "label_shown": bool(safe(lambda: v.ShowLabel, False))}


def _model_doc(s: Session, model: str):
    if not model:
        # the most recently active part/assembly
        for d in items(s.app.Documents.VisibleDocuments):
            if s.kind(d) in ("part", "assembly"):
                return d
        raise InventorError("no part/assembly open — give model=<path or document name>")
    if os.path.exists(model):
        return s.app.Documents.Open(os.path.abspath(model), False)
    for d in items(s.app.Documents):
        if safe(lambda d=d: d.DisplayName, "").lower().split(".")[0] == model.lower().split(".")[0]:
            return d
    raise InventorError(f"model {model!r} is neither a file nor an open document")


@tool("drawing")
def create_drawing(s: Session, standard: str = "AS1100", sheet_size: str = "A3", orientation: str = "landscape",
                   name: str = "") -> dict:
    """New drawing document (ISO template; AS1100 = third-angle projection, ISO = first-angle)."""
    app = s.app
    try:
        tpl = app.FileManager.GetTemplateFile(K.kDrawingDocumentObject, K.kMetricSystemOfMeasure, K.kISO_DraftingStandard)
    except Exception:
        tpl = ""
    d = app.Documents.Add(K.kDrawingDocumentObject, tpl, True)
    d.Activate()
    s.set_current(d)
    std = safe(lambda: d.StylesManager.ActiveStandardStyle)
    is_as = standard.upper().replace(" ", "") == "AS1100"
    if std is not None:
        safe(lambda: setattr(std, "FirstAngleProjection", not is_as))
        if is_as:       # AS 1100.101: decimal point, no trailing zeros
            od = safe(lambda: std.ActiveObjectDefaults)
            for attr in ("LinearDimensionStyle", "DiameterDimensionStyle", "RadialDimensionStyle",
                         "BaselineDimensionStyle"):
                ds = safe(lambda a=attr: getattr(od, a)) if od is not None else None
                if ds is not None:
                    safe(lambda ds=ds: setattr(ds, "DecimalMarkerType", K.kPeriodDecimalMarker))
                    safe(lambda ds=ds: setattr(ds, "TrailingZeroDisplay", False))
    sh = d.ActiveSheet
    _resize(sh, sheet_size, orientation)
    if name:
        safe(lambda: setattr(d, "DisplayName", name))
    return {"drawing": d.DisplayName, "standard": standard,
            "projection": "third-angle" if standard.upper().replace(" ", "") == "AS1100" else "first-angle",
            "sheet": _sheet_row(sh)}


def _resize(sh, size: str, orientation: str):
    key = SIZES.get(size.upper())
    if key:
        safe(lambda: setattr(sh, "Size", getattr(K, key)))
    safe(lambda: setattr(sh, "Orientation", K.kLandscapePageOrientation if orientation.startswith("l")
                         else K.kPortraitPageOrientation))


def _sheet_row(sh) -> dict:
    tb = safe(lambda: sh.TitleBlock)
    row = {"name": sh.Name, "size_mm": [r(sh.Width * 10, 1), r(sh.Height * 10, 1)],
           "views": sh.DrawingViews.Count}
    if tb is not None:
        rb = tb.RangeBox
        row["title_block_mm"] = [r(rb.MinPoint.X * 10, 1), r(rb.MinPoint.Y * 10, 1),
                                 r(rb.MaxPoint.X * 10, 1), r(rb.MaxPoint.Y * 10, 1)]
    return row


@tool("drawing")
def add_sheet(s: Session, sheet_size: str = "A3", orientation: str = "landscape", name: str = "") -> dict:
    """Add a sheet to the drawing (with the template's border and title block) and make it active."""
    d = s.drawing()
    size = getattr(K, SIZES.get(sheet_size.upper(), "kA3DrawingSheetSize"))
    orient = K.kLandscapePageOrientation if orientation.startswith("l") else K.kPortraitPageOrientation
    sh = d.Sheets.Add(size, orient, name) if name else d.Sheets.Add(size, orient)
    first = d.Sheets.Item(1)
    if safe(lambda: first.TitleBlock) is not None and safe(lambda: sh.TitleBlock) is None:
        safe(lambda: sh.AddTitleBlock(first.TitleBlock.Definition))
    if safe(lambda: first.Border) is not None and safe(lambda: sh.Border) is None:
        safe(lambda: sh.AddBorder(first.Border.Definition))
    sh.Activate()
    return {"sheet": _sheet_row(sh), "sheets": d.Sheets.Count}


@tool("drawing")
def activate_sheet(s: Session, sheet: str) -> dict:
    """Activate a sheet by name or 1-based index."""
    d = s.drawing()
    target = None
    if str(sheet).isdigit():
        target = d.Sheets.Item(int(sheet))
    else:
        for sh in items(d.Sheets):
            if sh.Name.lower().startswith(str(sheet).lower()):
                target = sh
    if target is None:
        raise InventorError(f"no sheet {sheet!r}")
    target.Activate()
    return {"sheet": _sheet_row(target)}


@tool("drawing")
def add_base_view(s: Session, model: str = "", x: float = 120.0, y: float = 170.0, scale: float = 1.0,
                  orientation: str = "front", style: str = "visible", name: str = "") -> dict:
    """Base view of a part/assembly (file path or open document name) centred at (x, y) sheet mm.

    scale: e.g. 0.5 for 1:2, 2 for 2:1
    orientation: front | top | right | left | back | bottom | iso | iso_left
    style: visible (hidden lines removed) | hidden | shaded | shaded_hidden
    """
    sh = _sheet(s)
    md = _model_doc(s, model)
    v = sh.DrawingViews.AddBaseView(md, s.tg.CreatePoint2d(x * MM, y * MM), float(scale),
                                    getattr(K, ORIENT[orientation.lower()]), getattr(K, STYLES[style.lower()]))
    if name:
        v.Name = name
    return {"view": _view_row(v)}


@tool("drawing")
def add_projected_view(s: Session, parent: str, x: float, y: float, style: str = "visible", name: str = "") -> dict:
    """Projected view from a parent view, placed at (x, y) sheet mm. Above/below/left/right gives the
    orthographic views (per the drawing's projection angle); a diagonal position gives an isometric."""
    sh = _sheet(s)
    v = sh.DrawingViews.AddProjectedView(_view(s, parent), s.tg.CreatePoint2d(x * MM, y * MM),
                                         getattr(K, STYLES.get(style.lower(), "kFromBaseDrawingViewStyle")))
    if name:
        v.Name = name
    return {"view": _view_row(v)}


def _settle(s: Session, v) -> bool:
    """If a new (unaligned) view overlaps another view, a parts list or the title block, move it to the
    first free spot on the sheet, scanning from the top-right. Returns True if it moved."""
    sh = _sheet(s)
    W, H = sh.Width * 10, sh.Height * 10
    tb = safe(lambda: sh.TitleBlock.RangeBox)
    blocked = [_lbox(o) for o in items(sh.DrawingViews) if o.Name != v.Name]
    if tb is not None:
        blocked.append((tb.MinPoint.X * 10, tb.MinPoint.Y * 10, tb.MaxPoint.X * 10, tb.MaxPoint.Y * 10))
    for pl in items(sh.PartsLists):
        rb = pl.RangeBox
        blocked.append((rb.MinPoint.X * 10, rb.MinPoint.Y * 10, rb.MaxPoint.X * 10, rb.MaxPoint.Y * 10))
    px, py = v.Position.X * 10, v.Position.Y * 10
    lb = _lbox(v)            # view + label, relative to the view's position
    rel = (lb[0] - px - 4, lb[1] - py - 4, lb[2] - px + 4, lb[3] - py + 4)

    def free(cx, cy):
        box = (cx + rel[0], cy + rel[1], cx + rel[2], cy + rel[3])
        if box[0] < 14 or box[1] < 14 or box[2] > W - 14 or box[3] > H - 14:
            return False
        return not any(_overlap(box, o) for o in blocked)

    if free(px, py):
        return False

    def try_at(x, y) -> bool:
        if not free(x, y):
            return False
        v.Position = s.tg.CreatePoint2d(x * MM, y * MM)
        ax, ay = v.Position.X * 10, v.Position.Y * 10      # aligned views snap back on one axis
        return free(ax, ay)

    # aligned (section/projected) views can only slide along one axis: try those lines first
    ys = [y for y in [py + k * 5.0 for k in range(-80, 81)] if 14 < y + rel[1] and y + rel[3] < H - 14]
    for y in sorted(ys, key=lambda y: abs(y - py)):
        if try_at(px, y):
            return True
    xs = [x for x in [px + k * 5.0 for k in range(-120, 121)] if 14 < x + rel[0] and x + rel[2] < W - 14]
    for x in sorted(xs, key=lambda x: abs(x - px)):
        if try_at(x, py):
            return True
    y = H - 14 - rel[3]
    while y + rel[1] > 14:
        x = W - 14 - rel[2]
        while x + rel[0] > 14:
            if try_at(x, y):
                return True
            x -= 5.0
        y -= 5.0
    v.Position = s.tg.CreatePoint2d(px * MM, py * MM)       # nowhere free: leave it for QA to report
    return False


@tool("drawing")
def add_section_view(s: Session, parent: str, x: float, y: float, cut: str = "vertical", offset: float = 0.0,
                     label: str = "A") -> dict:
    """Full section through a parent view along a straight cutting line, placed at (x, y) sheet mm.

    cut: vertical | horizontal — the cutting line direction on the parent view
    offset: mm on the sheet from the parent view's centre to the cutting line
    """
    sh = _sheet(s)
    pv = _view(s, parent)
    l, b0, rr, t = _box(pv)
    cx, cy = (l + rr) / 2, (b0 + t) / 2
    if cut.startswith("v"):
        ends = [(cx + offset, b0 - 6), (cx + offset, t + 6)]
    else:
        ends = [(l - 6, cy + offset), (rr + 6, cy + offset)]
    sk = pv.Sketches.Add()
    sk.Edit()
    pts = [sk.SheetToSketchSpace(s.tg.CreatePoint2d(px * MM, py * MM)) for px, py in ends]
    sk.SketchLines.AddByTwoPoints(pts[0], pts[1])
    sk.ExitEdit()
    v = sh.DrawingViews.AddSectionView(pv, sk, s.tg.CreatePoint2d(x * MM, y * MM), K.kFromBaseDrawingViewStyle,
                                       ShowLabel=True, Name=label)
    moved = safe(lambda: _settle(s, v), False)
    return {"view": _view_row(v), "moved_to_free_space": moved}


@tool("drawing")
def add_detail_view(s: Session, parent: str, center_x: float, center_y: float, radius: float, x: float, y: float,
                    scale: float = 2.0, label: str = "B") -> dict:
    """Circular detail (enlarged) view of part of a parent view. center/radius are sheet mm on the parent."""
    sh = _sheet(s)
    pv = _view(s, parent)
    v = sh.DrawingViews.AddDetailView(pv, s.tg.CreatePoint2d(x * MM, y * MM), K.kFromBaseDrawingViewStyle, True,
                                      s.tg.CreatePoint2d(center_x * MM, center_y * MM), radius * MM,
                                      Scale=float(scale), ShowLabel=True, Name=label)
    if abs(v.Scale - float(scale)) > 1e-9:
        safe(lambda: setattr(v, "ScaleFromBase", False))
        safe(lambda: setattr(v, "Scale", float(scale)))
    moved = safe(lambda: _settle(s, v), False)
    return {"view": _view_row(v), "moved_to_free_space": moved}


@tool("drawing")
def move_view(s: Session, view: str, x: float, y: float) -> dict:
    """Move a view's centre to (x, y) sheet mm (projected children follow alignment)."""
    v = _view(s, view)
    v.Position = s.tg.CreatePoint2d(x * MM, y * MM)
    return {"view": _view_row(v)}


@tool("drawing")
def set_view_scale(s: Session, view: str, scale: float) -> dict:
    """Change a base view's scale (dependent views follow)."""
    v = _view(s, view)
    v.Scale = float(scale)
    return {"view": _view_row(v)}


@tool("drawing", mutates=False)
def list_views(s: Session) -> dict:
    """Views on the active sheet: name, scale, centre, box, size, type."""
    sh = _sheet(s)
    return {"sheet": _sheet_row(sh), "views": [_view_row(v) for v in items(sh.DrawingViews)]}


def _model_entity(s: Session, v, kind: str, index: int, occurrence: str = ""):
    """Model edge/face (by part index) as seen in a drawing view."""
    md = v.ReferencedDocumentDescriptor.ReferencedDocument
    if s.kind(md) == "part":
        body = md.ComponentDefinition.SurfaceBodies.Item(1)
    else:
        if not occurrence:
            raise InventorError("assembly view: give occurrence= the component name")
        occ = None
        for o in items(md.ComponentDefinition.Occurrences):
            if o.Name.lower().startswith(occurrence.lower()):
                occ = o
        if occ is None:
            raise InventorError(f"no occurrence {occurrence!r}")
        body = occ.SurfaceBodies.Item(1)
    coll = body.Edges if kind == "edge" else body.Faces
    if not 1 <= index <= coll.Count:
        raise InventorError(f"{kind} {index} out of range 1..{coll.Count}")
    return coll.Item(index)


def drawing_curves(v, entity=None):
    """DrawingView.DrawingCurves is an indexed property with an optional argument, which late
    binding can't call; invoke it with explicit types."""
    import pythoncom
    import win32com.client.dynamic as dyn
    o = v._oleobj_
    memid = o.GetIDsOfNames("DrawingCurves")
    arg = entity._oleobj_ if entity is not None else pythoncom.Missing
    res = o.InvokeTypes(memid, 0, pythoncom.DISPATCH_PROPERTYGET, (pythoncom.VT_DISPATCH, 0),
                        ((pythoncom.VT_VARIANT, 17),), arg)
    return dyn.Dispatch(res)


def _curves(v, entity=None) -> list:
    try:
        return list(items(drawing_curves(v, entity)))
    except Exception:
        return []


def _pt(c):
    """A sheet point on a drawing curve (mid, else start, else centre)."""
    for attr in ("MidPoint", "StartPoint", "CenterPoint"):
        p = safe(lambda a=attr: getattr(c, a))
        if p is not None:
            return p
    return None


def _is_circle(c) -> bool:
    return safe(lambda: c.CurveType, 0) in (K.get("kCircleCurve"), K.get("kCircleCurve2d"))


@tool("drawing")
def add_linear_dimension(s: Session, view: str, edge_one: int, edge_two: int = 0, x: float = 0.0, y: float = 0.0,
                         direction: str = "auto", occurrence: str = "") -> dict:
    """Dimension a model edge's length (one edge) or the distance between two edges, in a view.
    Edge indices are the part's list_edges indices. (x, y) sheet mm for the text; 0,0 = auto.

    direction: auto | horizontal | vertical | aligned
    """
    sh = _sheet(s)
    v = _view(s, view)
    c1 = _curves(v, _model_entity(s, v, "edge", edge_one, occurrence))
    if not c1:
        raise InventorError(f"edge {edge_one} is not visible in view {v.Name}")
    i1 = sh.CreateGeometryIntent(c1[0])
    i2 = None
    if edge_two:
        c2 = _curves(v, _model_entity(s, v, "edge", edge_two, occurrence))
        if not c2:
            raise InventorError(f"edge {edge_two} is not visible in view {v.Name}")
        i2 = sh.CreateGeometryIntent(c2[0])
    if not (x or y):
        b = _box(v)
        mp = _pt(c1[0])
        x, y = mp.X * 10, b[3] + 8 if mp.Y * 10 > (b[1] + b[3]) / 2 else b[1] - 8
    dtype = {"horizontal": "kHorizontalDimensionType", "vertical": "kVerticalDimensionType",
             "aligned": "kAlignedDimensionType"}.get(direction)
    gd = sh.DrawingDimensions.GeneralDimensions
    tp = s.tg.CreatePoint2d(x * MM, y * MM)
    if i2 is not None:
        dim = gd.AddLinear(tp, i1, i2, getattr(K, dtype)) if dtype else gd.AddLinear(tp, i1, i2)
    else:
        dim = gd.AddLinear(tp, i1, None, getattr(K, dtype)) if dtype else gd.AddLinear(tp, i1)
    return {"dimension_mm": r(dim.ModelValue * 10, 3), "text": safe(lambda: dim.Text.Text, "")}


@tool("drawing")
def add_diameter_dimension(s: Session, view: str, edge: int, x: float = 0.0, y: float = 0.0, occurrence: str = "") -> dict:
    """Diameter dimension on a circular edge (list_edges type circle) in a view."""
    sh = _sheet(s)
    v = _view(s, view)
    c = _curves(v, _model_entity(s, v, "edge", edge, occurrence))
    if not c:
        raise InventorError(f"edge {edge} is not visible in view {v.Name}")
    if not (x or y):
        cp = c[0].CenterPoint
        x, y = cp.X * 10 + 15, cp.Y * 10 + 15
    dim = sh.DrawingDimensions.GeneralDimensions.AddDiameter(s.tg.CreatePoint2d(x * MM, y * MM),
                                                             sh.CreateGeometryIntent(c[0]))
    return {"dimension_mm": r(dim.ModelValue * 10, 3)}


@tool("drawing")
def auto_dimension_view(s: Session, view: str, arrange: bool = True) -> dict:
    """Retrieve the model's own (sketch + feature) dimensions into a view — the fastest way to a
    fully-dimensioned view — and optionally arrange them clear of the geometry."""
    sh = _sheet(s)
    v = _view(s, view)
    gd = sh.DrawingDimensions.GeneralDimensions
    try:
        got = gd.Retrieve(v)
        n = got.Count if got is not None else 0
    except Exception as e:
        return {"retrieved": 0, "note": f"no retrievable dimensions ({e.__class__.__name__}) — add them with add_linear_dimension"}
    if arrange and n:
        safe(lambda: sh.DrawingDimensions.Arrange(got))
    return {"retrieved": n, "view": v.Name}


@tool("drawing")
def add_centermarks(s: Session, view: str = "") -> dict:
    """Centre marks on every circular edge in a view (or all views on the sheet)."""
    sh = _sheet(s)
    views = [_view(s, view)] if view else list(items(sh.DrawingViews))
    n = 0
    for v in views:
        if "Iso" in K.name_of(safe(lambda v=v: v.Camera.ViewOrientationType, 0), "k"):
            continue
        seen = set()
        for c in _curves(v):
            if not _is_circle(c):
                continue
            cp = c.CenterPoint
            key = (round(cp.X, 3), round(cp.Y, 3))
            if key in seen:
                continue
            seen.add(key)
            if safe(lambda c=c: sh.Centermarks.Add(sh.CreateGeometryIntent(c)), None) is not None:
                n += 1
    return {"centermarks": n}


@tool("drawing")
def add_hole_note(s: Session, view: str, edge: int, x: float = 0.0, y: float = 0.0) -> dict:
    """Hole/thread note (Ø, depth, thread, counterbore...) on a hole's circular edge in a view."""
    sh = _sheet(s)
    v = _view(s, view)
    c = _curves(v, _model_entity(s, v, "edge", edge))
    if not c:
        raise InventorError(f"edge {edge} is not visible in view {v.Name}")
    if not (x or y):
        cp = c[0].CenterPoint
        x, y = cp.X * 10 + 18, cp.Y * 10 + 18
    note = sh.DrawingNotes.HoleThreadNotes.Add(s.tg.CreatePoint2d(x * MM, y * MM), c[0])
    return {"note": safe(lambda: note.Text, "")}


@tool("drawing")
def add_general_notes(s: Session, text: str, x: float = 20.0, y: float = 40.0) -> dict:
    """Free text note at (x, y) sheet mm (use \\n for new lines, e.g. "NOTES:\\n1. DEBURR ALL EDGES")."""
    sh = _sheet(s)
    note = sh.DrawingNotes.GeneralNotes.AddFitted(s.tg.CreatePoint2d(x * MM, y * MM),
                                                  text.replace("\\n", "\n").replace("\n", "<Br/>"))
    return {"note": safe(lambda: note.Text, text)}


@tool("drawing")
def add_parts_list(s: Session, view: str = "", x: float = 0.0, y: float = 0.0) -> dict:
    """Parts list (BOM table) for an assembly view; default position above the title block."""
    sh = _sheet(s)
    v = _view(s, view) if view else sh.DrawingViews.Item(1)
    if not (x or y):
        tb = safe(lambda: sh.TitleBlock.RangeBox)
        x = (tb.MaxPoint.X * 10) if tb is not None else sh.Width * 10 - 10
        y = (tb.MaxPoint.Y * 10 + 5) if tb is not None else 80
    pl = sh.PartsLists.Add(v, s.tg.CreatePoint2d(x * MM, y * MM))
    # Position is the table's top-right corner: lift it so its bottom clears the title block
    rb = pl.RangeBox
    height = (rb.MaxPoint.Y - rb.MinPoint.Y) * 10
    width = (rb.MaxPoint.X - rb.MinPoint.X) * 10
    if rb.MinPoint.Y * 10 < y:
        pl.Position = s.tg.CreatePoint2d(x * MM, (y + height) * MM)
    rb = pl.RangeBox
    return {"rows": pl.PartsListRows.Count, "box_mm": [r(rb.MinPoint.X * 10, 1), r(rb.MinPoint.Y * 10, 1),
                                                       r(rb.MaxPoint.X * 10, 1), r(rb.MaxPoint.Y * 10, 1)],
            "size_mm": [r(width, 1), r(height, 1)]}


@tool("drawing")
def auto_balloon(s: Session, view: str = "") -> dict:
    """Balloon every component visible in an assembly view, placed outside the view and linked to
    the parts list numbering."""
    sh = _sheet(s)
    if view:
        v = _view(s, view)
    else:       # an orthographic view shows outlines best
        vs = [w for w in items(sh.DrawingViews) if "Iso" not in K.name_of(safe(lambda w=w: w.Camera.ViewOrientationType, 0), "k")]
        v = vs[-1] if vs else sh.DrawingViews.Item(1)
    md = v.ReferencedDocumentDescriptor.ReferencedDocument
    if s.kind(md) != "assembly":
        raise InventorError("auto_balloon needs an assembly view")
    l, b, rgt, t = _box(v)
    cx, cy = (l + rgt) / 2, (b + t) / 2
    placed, done = 0, set()
    for occ in items(md.ComponentDefinition.Occurrences):
        fname = safe(lambda o=occ: o.Definition.Document.FullFileName, occ.Name)
        if fname in done:
            continue
        curves = _curves(v, occ)
        if not curves:
            continue
        c = next((cc for cc in curves if safe(lambda cc=cc: cc.MidPoint) is not None), curves[0])
        mp = _pt(c)
        if mp is None:
            continue
        dx, dy = mp.X * 10 - cx, mp.Y * 10 - cy
        n = math.hypot(dx, dy) or 1
        rad = max(rgt - l, t - b) / 2 + 12
        bx, by = cx + dx / n * rad, cy + dy / n * rad
        pts = s.collection([s.tg.CreatePoint2d(bx * MM, by * MM), sh.CreateGeometryIntent(c)])
        if safe(lambda: sh.Balloons.Add(pts), None) is not None:
            placed += 1
            done.add(fname)
    return {"balloons": placed, "view": v.Name}


TB_FIELDS = {"title": ("Inventor Summary Information", "Title"), "drawing_number": ("Design Tracking Properties", "Part Number"),
             "part_number": ("Design Tracking Properties", "Part Number"), "drawn_by": ("Inventor Summary Information", "Author"),
             "author": ("Inventor Summary Information", "Author"), "designer": ("Design Tracking Properties", "Designer"),
             "checked_by": ("Design Tracking Properties", "Checked By"), "approved_by": ("Design Tracking Properties", "Engineer Approved By"),
             "revision": ("Inventor Summary Information", "Revision Number"), "description": ("Design Tracking Properties", "Description"),
             "company": ("Inventor Document Summary Information", "Company"), "material": ("Design Tracking Properties", "Material"),
             "project": ("Design Tracking Properties", "Project"), "subject": ("Inventor Summary Information", "Subject")}


@tool("drawing")
def set_title_block_field(s: Session, fields: dict) -> dict:
    """Fill title-block fields: title, drawing_number, drawn_by, checked_by, approved_by, revision,
    description, company, material, project. Writes the drawing's iProperties (which the title
    block shows) and any prompted entries with a matching name."""
    d = s.drawing()
    done = {}
    for k, val in fields.items():
        key = k.lower().replace(" ", "_")
        if key in TB_FIELDS:
            setname, prop = TB_FIELDS[key]
            ok = safe(lambda: setattr(d.PropertySets.Item(setname).Item(prop), "Value", str(val)) or True, False)
            if ok:
                done[key] = str(val)
        tb = safe(lambda: d.ActiveSheet.TitleBlock)
        if tb is not None:
            for tbx in items(tb.Definition.Sketch.TextBoxes):
                txt = safe(lambda t=tbx: t.Text, "")
                if "<" in txt and k.lower().replace("_", " ") in txt.lower():
                    if safe(lambda t=tbx: tb.SetPromptResultText(t, str(val)) or True, False):
                        done[key] = str(val)
    d.Update()
    return {"set": done, "ignored": [k for k in fields if k.lower().replace(" ", "_") not in done]}


@tool("drawing")
def place_view_labels(s: Session) -> dict:
    """Show a label (name + scale) under every view; names views FRONT/TOP/RIGHT/ISO... from their
    orientation when they still have default names."""
    sh = _sheet(s)
    names = {"kFrontViewOrientation": "FRONT", "kTopViewOrientation": "TOP", "kRightViewOrientation": "RIGHT",
             "kLeftViewOrientation": "LEFT", "kBottomViewOrientation": "BOTTOM", "kBackViewOrientation": "BACK",
             "kIsoTopRightViewOrientation": "ISOMETRIC", "kIsoTopLeftViewOrientation": "ISOMETRIC"}
    out = []
    for v in items(sh.DrawingViews):
        o = K.name_of(safe(lambda v=v: v.Camera.ViewOrientationType, 0), "k")
        if v.Name.upper().startswith("VIEW") and o in names:
            safe(lambda v=v: setattr(v, "Name", names[o] + ("" if names[o] not in [x["name"] for x in out] else " 2")))
        v.ShowLabel = True
        out.append({"name": v.Name, "scale": _scale_text(v.Scale)})
    return {"labels": out}


# --------------------------------------------------------------------------- one-shot sheets
def _region(sh) -> dict:
    """Free drawing area: inside a 10 mm border margin and above the title block band."""
    W, H = sh.Width * 10, sh.Height * 10
    tb = safe(lambda: sh.TitleBlock.RangeBox)
    tb_top = tb.MaxPoint.Y * 10 if tb is not None else 10.0
    tb_left = tb.MinPoint.X * 10 if tb is not None else W
    return {"x0": 22.0, "x1": W - 14.0, "y0": tb_top + 14.0, "y1": H - 14.0, "W": W, "H": H,
            "tb_left": tb_left, "tb_top": tb_top}


def _pick_scale(extent_w: float, extent_h: float, avail_w: float, avail_h: float) -> float:
    for sc in STANDARD_SCALES:
        if extent_w * sc <= avail_w and extent_h * sc <= avail_h:
            return sc
    return STANDARD_SCALES[-1]


def _extents(md) -> list[float]:
    rb = md.ComponentDefinition.RangeBox
    return [(rb.MaxPoint.X - rb.MinPoint.X) * 10, (rb.MaxPoint.Y - rb.MinPoint.Y) * 10,
            (rb.MaxPoint.Z - rb.MinPoint.Z) * 10]


def _layout(s: Session, md, want: list[str], third: bool, scale: float, label_gap: float = 14.0,
            gap: float = 22.0) -> dict:
    """Place FRONT (+TOP/+RIGHT projected) in the left ~70 % of the free area and an ISOMETRIC in the
    top-right, all clear of the title block. Inventor's Front view of a part shows X across and Y up."""
    sh = _sheet(s)
    g = _region(sh)
    L = _extents(md)
    fw, fh = L[0], L[1]
    tw, th = L[0], L[2]
    rw, rh = L[2], L[1]
    has_top, has_right = "top" in want, "right" in want
    dm = 30.0          # room left of / below the views for dimensions
    g = dict(g, x0=g["x0"] + dm, y0=g["y0"] + dm * 0.6)
    block_w = (g["x1"] - g["x0"]) * 0.66
    block_h = g["y1"] - g["y0"]
    need_w = fw + (rw if has_right else 0)
    need_h = fh + (th if has_top else 0)
    avail_w = block_w - (gap if has_right else 0)
    avail_h = block_h - (gap if has_top else 0) - label_gap * (2 if has_top else 1)
    sc = scale or _pick_scale(need_w, need_h, avail_w, avail_h)
    used_w = need_w * sc + (gap if has_right else 0)
    used_h = need_h * sc + (gap + label_gap if has_top else 0)
    left = g["x0"] + (block_w - used_w) / 2
    bottom = g["y0"] + (block_h - used_h - label_gap) / 2
    if third:
        fx = left + fw * sc / 2
        fy = bottom + fh * sc / 2
        top_y = fy + fh * sc / 2 + gap + label_gap + th * sc / 2
        right_x = fx + fw * sc / 2 + gap + rw * sc / 2
    else:
        fx = left + (rw * sc + gap if has_right else 0) + fw * sc / 2
        fy = bottom + (th * sc + gap + label_gap if has_top else 0) + fh * sc / 2
        top_y = fy - fh * sc / 2 - gap - label_gap - th * sc / 2
        right_x = fx - fw * sc / 2 - gap - rw * sc / 2
    src = md.FullFileName or md.DisplayName
    made = [add_base_view(s, model=src, x=fx, y=fy, scale=sc, orientation="front", name="FRONT")["view"]]
    if has_top:
        made.append(add_projected_view(s, "FRONT", fx, top_y, name="TOP")["view"])
    if has_right:
        made.append(add_projected_view(s, "FRONT", right_x, fy, name="RIGHT")["view"])
    if "iso" in want:
        iso_x0 = g["x0"] + block_w + 10
        iso_w, iso_h = g["x1"] - iso_x0, (g["y1"] - g["y0"]) * 0.55
        diag = math.sqrt(L[0] ** 2 + L[1] ** 2 + L[2] ** 2) or 1
        iso_sc = _pick_scale(diag, diag * 0.85, iso_w - 10, iso_h - label_gap)
        iso_sc = min(iso_sc, sc)
        v = sh.DrawingViews.AddBaseView(md, s.tg.CreatePoint2d((iso_x0 + iso_w / 2) * MM,
                                                               (g["y1"] - iso_h / 2) * MM), iso_sc,
                                        K.kIsoTopRightViewOrientation, K.kShadedDrawingViewStyle)
        v.Name = "ISOMETRIC"
        made.append(_view_row(v))
    return {"scale": sc, "views": made}


def _hole_position_dims(s: Session, view_name: str) -> int:
    """Locate every circle in an orthographic view from the view's left and bottom outline edges
    (one dimension per distinct x and per distinct y)."""
    sh = _sheet(s)
    v = _view(s, view_name)
    curves = _curves(v)
    lines = [c for c in curves if safe(lambda c=c: c.CurveType, 0) in (K.get("kLineSegmentCurve"), K.get("kLineSegmentCurve2d"))]
    circles = [c for c in curves if _is_circle(c)]
    if not lines or not circles:
        return 0
    def xs(c):
        a, b = c.StartPoint, c.EndPoint
        return a, b
    verticals = [c for c in lines if abs(xs(c)[0].X - xs(c)[1].X) < 1e-6]
    horizontals = [c for c in lines if abs(xs(c)[0].Y - xs(c)[1].Y) < 1e-6]
    if not verticals or not horizontals:
        return 0
    left = min(verticals, key=lambda c: c.StartPoint.X)
    bottom = min(horizontals, key=lambda c: c.StartPoint.Y)
    b = _box(v)
    gd = sh.DrawingDimensions.GeneralDimensions
    n, done_x, done_y = 0, set(), set()
    centres = {}
    for c in circles:
        cp = c.CenterPoint
        centres.setdefault((round(cp.X, 3), round(cp.Y, 3)), c)
    for k, ((cx, cy), c) in enumerate(sorted(centres.items())):
        if round(cx, 2) not in done_x and abs(cx - left.StartPoint.X) > 1e-4:
            ty = b[1] - 8 - 8 * len(done_x)
            dim = safe(lambda: gd.AddLinear(s.tg.CreatePoint2d(cx, ty * MM), sh.CreateGeometryIntent(left),
                                            sh.CreateGeometryIntent(c, K.kCenterPointIntent),
                                            K.kHorizontalDimensionType))
            if dim is not None:
                n += 1
                done_x.add(round(cx, 2))
        if round(cy, 2) not in done_y and abs(cy - bottom.StartPoint.Y) > 1e-4:
            tx = b[0] - 8 - 8 * len(done_y)
            dim = safe(lambda: gd.AddLinear(s.tg.CreatePoint2d(tx * MM, cy), sh.CreateGeometryIntent(bottom),
                                            sh.CreateGeometryIntent(c, K.kCenterPointIntent),
                                            K.kVerticalDimensionType))
            if dim is not None:
                n += 1
                done_y.add(round(cy, 2))
    return n


def _tidy_dimension_text(s: Session) -> int:
    """Pull dimension text that landed outside the drawing area (or on the title block) back in."""
    sh = _sheet(s)
    g = _region(sh)
    moved = 0
    for dim in items(sh.DrawingDimensions):
        o = safe(lambda dim=dim: dim.Text.Origin)
        if o is None:
            continue
        x, y = o.X * 10, o.Y * 10
        nx = min(max(x, 16.0), g["W"] - 16.0)
        ny = min(max(y, 16.0), g["H"] - 16.0)
        if x > g["tb_left"] - 4 and ny < g["tb_top"] + 6:
            ny = g["tb_top"] + 8
        if (nx, ny) != (x, y):
            if safe(lambda dim=dim: setattr(dim.Text, "Origin", s.tg.CreatePoint2d(nx * MM, ny * MM)) or True, False):
                moved += 1
    return moved


@tool("drawing")
def make_part_sheet(s: Session, model: str = "", views: str = "front,top,right,iso", scale: float = 0.0,
                    sheet_size: str = "A3", standard: str = "AS1100", dimensions: bool = True,
                    title: str = "", drawing_number: str = "", drawn_by: str = "", material: str = "") -> dict:
    """One-shot detail drawing of a part: new drawing, FRONT + projected TOP/RIGHT laid out for the
    projection angle and clear of the title block, a shaded ISOMETRIC, retrieved model dimensions,
    hole position dimensions, centre marks, view labels, title block — then QA. Always render_sheet
    and look, and fix what check_drawing reports.

    views: comma list from front, top, right, iso
    scale: 0 = largest standard scale that fits
    """
    md = _model_doc(s, model)
    if s.kind(md) != "part":
        raise InventorError("make_part_sheet needs a part (use make_assembly_sheet for assemblies)")
    third = standard.upper().replace(" ", "") == "AS1100"
    create_drawing(s, standard=standard, sheet_size=sheet_size)
    want = [w.strip().lower() for w in views.split(",") if w.strip()]
    lay = _layout(s, md, want, third, scale)
    steps: dict = {}
    ortho = [m["name"] for m in lay["views"] if m["name"] != "ISOMETRIC"]
    if dimensions:
        steps["retrieved"] = sum(auto_dimension_view(s, vn, arrange=True).get("retrieved", 0) for vn in ortho)
        steps["hole_positions"] = safe(lambda: _hole_position_dims(s, "FRONT"), 0)
        steps["centermarks"] = safe(lambda: add_centermarks(s)["centermarks"], 0)
        sh = _sheet(s)
        safe(lambda: sh.DrawingDimensions.Arrange(s.collection(list(items(sh.DrawingDimensions.GeneralDimensions)))))
        steps["text_moved"] = safe(lambda: _tidy_dimension_text(s), 0)
    place_view_labels(s)
    fields = {k: v for k, v in (("title", title or md.DisplayName.split(".")[0].upper()),
                                ("drawing_number", drawing_number or safe(lambda: str(md.PropertySets.Item(
                                    "Design Tracking Properties").Item("Part Number").Value), "")),
                                ("drawn_by", drawn_by), ("material", material or safe(
                                    lambda: md.ActiveMaterial.DisplayName, ""))) if v}
    set_title_block_field(s, fields)
    return {"scale": _scale_text(lay["scale"]), "views": [m["name"] for m in lay["views"]], **steps,
            "qa": check_drawing(s)}


@tool("drawing")
def make_assembly_sheet(s: Session, model: str = "", scale: float = 0.0, sheet_size: str = "A3",
                        standard: str = "AS1100", title: str = "", drawing_number: str = "",
                        drawn_by: str = "") -> dict:
    """One-shot general-arrangement (GA) drawing of an assembly: FRONT + TOP, shaded ISOMETRIC, parts
    list above the title block, balloons, labels, title block, QA."""
    md = _model_doc(s, model)
    if s.kind(md) != "assembly":
        raise InventorError("make_assembly_sheet needs an assembly")
    third = standard.upper().replace(" ", "") == "AS1100"
    create_drawing(s, standard=standard, sheet_size=sheet_size)
    lay = _layout(s, md, ["front", "top", "iso"], third, scale)
    pl = add_parts_list(s, "FRONT")
    # if the iso view now collides with the parts list, shrink it toward the top-right
    sh = _sheet(s)
    iso = next((v for v in items(sh.DrawingViews) if v.Name == "ISOMETRIC"), None)
    if iso is not None:
        for _ in range(4):
            if not _overlap(_box(iso), pl["box_mm"], 1):
                break
            iso.Scale = iso.Scale * 0.75
            b = _box(iso)
            g = _region(sh)
            iso.Position = s.tg.CreatePoint2d((g["x1"] - (b[2] - b[0]) / 2 - 2) * MM,
                                              (g["y1"] - (b[3] - b[1]) / 2 - 2) * MM)
    bl = auto_balloon(s)
    place_view_labels(s)
    set_title_block_field(s, {k: v for k, v in (("title", title or md.DisplayName.split(".")[0].upper()),
                                                ("drawing_number", drawing_number), ("drawn_by", drawn_by)) if v})
    return {"scale": _scale_text(lay["scale"]), "parts_list_rows": pl["rows"], "balloons": bl["balloons"],
            "qa": check_drawing(s)}


# --------------------------------------------------------------------------- QA, render, PDF
def _text_box(dim):
    """Approximate box of a dimension's text (3.5 mm text; vertical dimensions read rotated)."""
    o = safe(lambda: dim.Text.Origin)
    txt = safe(lambda: dim.Text.Text, "") or ""
    if o is None or not txt:
        return None
    w, h = max(len(txt), 1) * 2.6, 4.0
    if safe(lambda: dim.DimensionType, 0) == K.get("kVerticalDimensionType"):
        w, h = h, w
    x, y = o.X * 10, o.Y * 10
    return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def _overlap(a, b, pad=0.0) -> bool:
    return a[0] < b[2] - pad and b[0] < a[2] - pad and a[1] < b[3] - pad and b[1] < a[3] - pad


@tool("drawing", mutates=False)
def check_drawing(s: Session) -> dict:
    """QA of every sheet: views overlapping each other / the title block / the sheet edge, views
    with no dimensions, empty title-block fields, missing parts list or balloons on assemblies.
    Ends with TOTAL ISSUES: N — aim for 0, then render_sheet and look."""
    d = s.drawing()
    issues: list[str] = []
    for sh in items(d.Sheets):
        W, H = sh.Width * 10, sh.Height * 10
        tb = safe(lambda: sh.TitleBlock.RangeBox)
        tbox = (tb.MinPoint.X * 10, tb.MinPoint.Y * 10, tb.MaxPoint.X * 10, tb.MaxPoint.Y * 10) if tb is not None else None
        views = list(items(sh.DrawingViews))
        boxes = [(v.Name, _lbox(v)) for v in views]
        if not views:
            issues.append(f"[{sh.Name}] sheet has no views")
        for i, (n1, b1) in enumerate(boxes):
            if b1[0] < 10 or b1[1] < 10 or b1[2] > W - 10 or b1[3] > H - 10:
                issues.append(f"[{sh.Name}] view {n1} runs outside the border area")
            if tbox and _overlap(b1, tbox, 1):
                issues.append(f"[{sh.Name}] view {n1} overlaps the title block")
            for n2, b2 in boxes[i + 1:]:
                if _overlap(b1, b2, 2):
                    issues.append(f"[{sh.Name}] views {n1} and {n2} overlap")
        for pl in items(sh.PartsLists):
            rb = pl.RangeBox
            pb = (rb.MinPoint.X * 10, rb.MinPoint.Y * 10, rb.MaxPoint.X * 10, rb.MaxPoint.Y * 10)
            if tbox and _overlap(pb, tbox, 1):
                issues.append(f"[{sh.Name}] parts list overlaps the title block")
            for n1, b1 in boxes:
                if _overlap(pb, b1, 1):
                    issues.append(f"[{sh.Name}] parts list overlaps view {n1}")
        off = 0
        on_tb = 0
        for dim in items(sh.DrawingDimensions):
            o = safe(lambda dim=dim: dim.Text.Origin)
            if o is None:
                continue
            x, y = o.X * 10, o.Y * 10
            if x < 12 or y < 12 or x > W - 12 or y > H - 12:
                off += 1
            elif tbox and tbox[0] < x < tbox[2] and tbox[1] < y < tbox[3]:
                on_tb += 1
        if off:
            issues.append(f"[{sh.Name}] {off} dimension text(s) outside the border")
        texts = []
        for dim in items(sh.DrawingDimensions):
            box = _text_box(dim)
            if box:
                texts.append((safe(lambda dim=dim: dim.Text.Text, "?"), box))
        clash = [(a[0], b[0]) for i, a in enumerate(texts) for b in texts[i + 1:] if _overlap(a[1], b[1], 0.3)]
        if clash:
            issues.append(f"[{sh.Name}] overlapping dimension texts: " + ", ".join(f"{a} / {b}" for a, b in clash[:6]))
        if on_tb:
            issues.append(f"[{sh.Name}] {on_tb} dimension text(s) on the title block")
        # dimensions per view (by attachment)
        per_view = {v.Name: 0 for v in views}
        for dim in items(sh.DrawingDimensions):
            vn = None
            for path in ("IntentOne.Geometry.Parent", "Intent.Geometry.Parent",
                         "IntentOne.Geometry.Parent.Parent", "Intent.Geometry.Parent.Parent"):
                obj = dim
                for attr in path.split("."):
                    obj = safe(lambda o=obj, a=attr: getattr(o, a))
                    if obj is None:
                        break
                name = safe(lambda o=obj: o.Name) if obj is not None else None
                if name in per_view:
                    vn = name
                    break
            if vn is None:      # retrieved model dimensions: attribute by where the text sits
                o = safe(lambda dim=dim: dim.Text.Origin)
                if o is not None:
                    x, y = o.X * 10, o.Y * 10
                    near = [(n, b) for n, b in boxes if b[0] - 30 <= x <= b[2] + 30 and b[1] - 30 <= y <= b[3] + 30]
                    if near:
                        vn = min(near, key=lambda nb: abs(x - (nb[1][0] + nb[1][2]) / 2) + abs(y - (nb[1][1] + nb[1][3]) / 2))[0]
            if vn in per_view:
                per_view[vn] += 1
        ortho = [v for v in views if "Iso" not in K.name_of(safe(lambda v=v: v.Camera.ViewOrientationType, 0), "k")]
        is_asm = any(s.kind(safe(lambda v=v: v.ReferencedDocumentDescriptor.ReferencedDocument)) == "assembly"
                     for v in views if safe(lambda v=v: v.ReferencedDocumentDescriptor.ReferencedDocument) is not None)
        if not is_asm and ortho and sum(per_view.values()) == 0:
            issues.append(f"[{sh.Name}] no dimensions on any view")
        if is_asm:
            if sh.PartsLists.Count == 0:
                issues.append(f"[{sh.Name}] assembly sheet without a parts list")
            elif sh.Balloons.Count == 0:
                issues.append(f"[{sh.Name}] parts list but no balloons")
            elif sh.Balloons.Count < sh.PartsLists.Item(1).PartsListRows.Count:
                issues.append(f"[{sh.Name}] {sh.PartsLists.Item(1).PartsListRows.Count - sh.Balloons.Count} "
                              f"parts-list items have no balloon")
        for v in views:
            if not safe(lambda v=v: v.ShowLabel, False):
                issues.append(f"[{sh.Name}] view {v.Name} has no label")
    for key in ("title", "drawing_number", "drawn_by"):
        setname, prop = TB_FIELDS[key]
        if not safe(lambda: str(d.PropertySets.Item(setname).Item(prop).Value).strip(), ""):
            issues.append(f"title block field '{key}' is empty")
    report = "\n".join(f"- {i}" for i in issues) + f"\nTOTAL ISSUES: {len(issues)}"
    return {"issues": issues, "total": len(issues), "report": report}


@tool("drawing", mutates=False)
def render_sheet(s: Session, path: str = "", width: int = 2400) -> dict:
    """PNG of the active sheet (look at it before exporting)."""
    d = s.drawing()
    sh = d.ActiveSheet
    if not path:
        path = os.path.join(s.workdir, "renders", f"sheet-{int(time.time() * 1000)}.png")
    elif not os.path.isabs(path):
        path = os.path.join(s.workdir, "renders", path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    d.Activate()
    v = s.app.ActiveView
    safe(lambda: v.Fit())
    h = int(width * sh.Height / sh.Width)
    v.SaveAsBitmap(path, int(width), h)
    return {"path": path, "sheet": sh.Name}


@tool("drawing", mutates=False)
def export_pdf(s: Session, path: str, all_sheets: bool = True) -> dict:
    """Export the drawing (all sheets by default) to PDF, vector, black lines."""
    d = s.drawing()
    if not os.path.isabs(path):
        path = os.path.join(s.workdir, "exports", path)
    if not path.lower().endswith(".pdf"):
        path += ".pdf"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    app = s.app
    tr = app.ApplicationAddIns.ItemById(PDF_TRANSLATOR)
    ctx = app.TransientObjects.CreateTranslationContext()
    ctx.Type = K.kFileBrowseIOMechanism
    opts = app.TransientObjects.CreateNameValueMap()
    medium = app.TransientObjects.CreateDataMedium()
    medium.FileName = path
    for key, val in (("All_Color_AS_Black", 1), ("Remove_Line_Weights", 0), ("Vector_Resolution", 400),
                     ("Sheet_Range", K.kPrintAllSheets if all_sheets else K.kPrintCurrentSheet)):
        safe(lambda: opts.Add(key, val))
    if os.path.exists(path):
        os.remove(path)
    tr.SaveCopyAs(d, ctx, opts, medium)
    if not os.path.exists(path):
        raise InventorError("PDF translator did not write the file")
    return {"path": path, "bytes": os.path.getsize(path), "sheets": d.Sheets.Count if all_sheets else 1}
