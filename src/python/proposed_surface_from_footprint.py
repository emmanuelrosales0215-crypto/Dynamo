# Proposed Surface From Footprint
# -----------------------------------------------------------------------------
# Builds a proposed TIN surface from a pad/site footprint, daylighting out at a
# design slope until it catches an existing-ground surface. Everything runs
# inside Civil 3D through the native .NET API - no Dynamo packages required.
#
# Paste into a single Python Script node in Dynamo for Civil 3D (2024 or older).
# Written for both IronPython2 and CPython3 (no f-strings).
#
# INPUTS
#   IN[0]  eg_surface_name      string  name of the existing ground TIN surface
#   IN[1]  footprint_layer      string  layer holding the footprint polyline(s)
#   IN[2]  out_surface_name     string  name for the proposed surface
#   IN[3]  cut_slope            double  run:rise, e.g. 3.0 for 3:1
#   IN[4]  fill_slope           double  run:rise, e.g. 4.0 for 4:1
#   IN[5]  interval             double  densification interval, drawing units
#   IN[6]  max_search           double  give up daylighting past this distance
#   IN[7]  design_elevation     double or None. None = use the footprint's own Z
#
# OUTPUT
#   [status, catch_point_count, [failed_stations], [messages]]
# -----------------------------------------------------------------------------

import clr

clr.AddReference('AcMgd')
clr.AddReference('AcCoreMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AecBaseMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import *
from Autodesk.AutoCAD.DatabaseServices import *
from Autodesk.AutoCAD.Geometry import *
from Autodesk.Civil.ApplicationServices import *
from Autodesk.Civil.DatabaseServices import *

# --- inputs ------------------------------------------------------------------
eg_surface_name  = IN[0]
footprint_layer  = IN[1]
out_surface_name = IN[2]
cut_slope        = float(IN[3])
fill_slope       = float(IN[4])
interval         = float(IN[5])
max_search       = float(IN[6])
design_elevation = IN[7] if len(IN) > 7 else None

# Breakline tuning. 0 disables weeding/supplementing, which is what you want for
# a computed daylight line - let the solver's points survive verbatim.
MID_ORDINATE     = 0.1
MAX_DISTANCE     = 0.0
WEEDING_DISTANCE = 0.0
WEEDING_ANGLE    = 0.0

WORK_LAYER = "_C3D-AUTO-GRADING"   # breaklines land here; wiped on each run
BISECT_ITERATIONS = 40

messages = []
failed_stations = []


def eg_elevation(surface, x, y):
    """Elevation of the EG surface at (x, y), or None if outside its boundary."""
    try:
        return surface.FindElevationAtXY(x, y)
    except:
        return None


def signed_area(pts):
    """Shoelace on the XY projection. Positive = counter-clockwise winding."""
    total = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i][0], pts[i][1]
        x2, y2 = pts[(i + 1) % n][0], pts[(i + 1) % n][1]
        total += (x1 * y2) - (x2 * y1)
    return total / 2.0


def outward_normal(pts, i, ccw):
    """Unit horizontal normal pointing away from the footprint interior.

    For CCW winding the interior is on the left of travel, so the outward
    (right) normal of tangent (tx, ty) is (ty, -tx). Flip it for CW.
    """
    n = len(pts)
    prev_pt = pts[(i - 1) % n]
    next_pt = pts[(i + 1) % n]
    tx = next_pt[0] - prev_pt[0]
    ty = next_pt[1] - prev_pt[1]
    mag = (tx * tx + ty * ty) ** 0.5
    if mag < 1e-9:
        return None
    tx, ty = tx / mag, ty / mag
    nx, ny = (ty, -tx) if ccw else (-ty, tx)
    return (nx, ny)


def solve_catch_point(surface, x, y, z_design, nx, ny):
    """March outward, then bisect, to find where the design slope meets EG.

    Returns (x, y, z) or None if it never daylights within max_search.

    Deliberately uses sampling rather than Surface.GetIntersectionPoint: the
    ray-cast is faster but its behaviour with a sloped vector at a surface
    boundary is not documented, and this solver is verifiable by hand.
    """
    z_eg_start = eg_elevation(surface, x, y)
    if z_eg_start is None:
        return None

    if z_design > z_eg_start:
        slope, vertical = fill_slope, -1.0   # above EG: fill, project down
    else:
        slope, vertical = cut_slope, 1.0     # below EG: cut, project up
    if slope <= 0:
        return None

    def difference(dist):
        """Projected slope elevation minus EG elevation at that distance out."""
        px, py = x + nx * dist, y + ny * dist
        z_eg = eg_elevation(surface, px, py)
        if z_eg is None:
            return None
        return (z_design + vertical * (dist / slope)) - z_eg

    prev_d = 0.0
    prev_diff = difference(0.0)
    if prev_diff is None:
        return None

    step = interval
    d = step
    while d <= max_search:
        diff = difference(d)
        if diff is None:
            return None                       # ran off the edge of EG
        if diff == 0.0:
            return (x + nx * d, y + ny * d, z_design + vertical * (d / slope))
        if (diff > 0) != (prev_diff > 0):     # sign change brackets the catch
            lo, hi = prev_d, d
            for _ in range(BISECT_ITERATIONS):
                mid = (lo + hi) / 2.0
                mid_diff = difference(mid)
                if mid_diff is None:
                    return None
                if (mid_diff > 0) == (prev_diff > 0):
                    lo = mid
                else:
                    hi = mid
            final = (lo + hi) / 2.0
            return (x + nx * final,
                    y + ny * final,
                    z_design + vertical * (final / slope))
        prev_d, prev_diff = d, diff
        d += step

    return None


def ensure_layer(t, db, name):
    lt = t.GetObject(db.LayerTableId, OpenMode.ForRead)
    if lt.Has(name):
        return lt[name]
    lt.UpgradeOpen()
    ltr = LayerTableRecord()
    ltr.Name = name
    lid = lt.Add(ltr)
    t.AddNewlyCreatedDBObject(ltr, True)
    return lid


def wipe_layer(t, db, name):
    """Erase everything previously created on the work layer - keeps re-runs idempotent."""
    bt = t.GetObject(db.BlockTableId, OpenMode.ForRead)
    btr = t.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead)
    doomed = []
    for oid in btr:                       # collect first - never erase mid-iteration
        ent = t.GetObject(oid, OpenMode.ForRead)
        if getattr(ent, "Layer", None) == name:
            doomed.append(oid)
    for oid in doomed:
        ent = t.GetObject(oid, OpenMode.ForWrite)
        ent.Erase()


def make_polyline3d(t, db, points, closed, layer_id):
    pts = Point3dCollection()
    for p in points:
        pts.Add(Point3d(p[0], p[1], p[2]))
    pl = Polyline3d(Poly3dType.SimplePoly, pts, closed)
    pl.LayerId = layer_id
    bt = t.GetObject(db.BlockTableId, OpenMode.ForRead)
    btr = t.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite)
    btr.AppendEntity(pl)
    t.AddNewlyCreatedDBObject(pl, True)
    return pl


# --- main --------------------------------------------------------------------
def build():
    """Returns [status, catch_point_count, failed_stations, messages]."""
    adoc = Application.DocumentManager.MdiActiveDocument
    civdoc = CivilApplication.ActiveDocument
    db = adoc.Database

    catch_count = 0

    with adoc.LockDocument():
      with db.TransactionManager.StartTransaction() as t:

        # locate the existing ground surface by name
        eg = None
        for sid in civdoc.GetSurfaceIds():
            s = t.GetObject(sid, OpenMode.ForRead)
            if s.Name == eg_surface_name:
                eg = s
                break
        if eg is None:
            return ["failed", 0, [],
                    ["EG surface '{0}' not found.".format(eg_surface_name)]]

        # drop any prior run's proposed surface, then its breaklines
        for sid in civdoc.GetSurfaceIds():
            s = t.GetObject(sid, OpenMode.ForRead)
            if s.Name == out_surface_name:
                s.UpgradeOpen()
                s.Erase()
                messages.append("Replaced existing surface '{0}'.".format(out_surface_name))
                break

        layer_id = ensure_layer(t, db, WORK_LAYER)
        wipe_layer(t, db, WORK_LAYER)

        # gather footprint curves off the input layer
        bt = t.GetObject(db.BlockTableId, OpenMode.ForRead)
        btr = t.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead)
        curves = []
        for oid in btr:
            ent = t.GetObject(oid, OpenMode.ForRead)
            if isinstance(ent, Curve) and ent.Layer == footprint_layer:
                curves.append(ent)
        if not curves:
            return ["failed", 0, [],
                    ["No curves found on layer '{0}'.".format(footprint_layer)]]

        breakline_ids = ObjectIdCollection()
        daylight_ids = ObjectIdCollection()

        for curve in curves:
            # densify the footprint
            try:
                length = curve.GetDistanceAtParameter(curve.EndParam)
            except:
                messages.append("Skipped a curve whose length could not be measured.")
                continue

            samples = []
            d = 0.0
            while d < length:
                p = curve.GetPointAtDist(d)
                z = float(design_elevation) if design_elevation is not None else p.Z
                samples.append((p.X, p.Y, z))
                d += interval
            if len(samples) < 3:
                messages.append("Skipped a curve with fewer than 3 sample points.")
                continue

            closed = bool(curve.Closed)
            ccw = signed_area(samples) > 0

            catch_points = []
            for i in range(len(samples)):
                x, y, z = samples[i]
                normal = outward_normal(samples, i, ccw)
                if normal is None:
                    continue
                hit = solve_catch_point(eg, x, y, z, normal[0], normal[1])
                if hit is None:
                    failed_stations.append(round(i * interval, 3))
                else:
                    catch_points.append(hit)

            if len(catch_points) < 3:
                messages.append("A footprint produced too few catch points to daylight.")
                continue

            pad_pl = make_polyline3d(t, db, samples, closed, layer_id)
            day_pl = make_polyline3d(t, db, catch_points, closed, layer_id)
            breakline_ids.Add(pad_pl.ObjectId)
            breakline_ids.Add(day_pl.ObjectId)
            daylight_ids.Add(day_pl.ObjectId)
            catch_count += len(catch_points)

        if breakline_ids.Count == 0:
            return ["failed", 0, failed_stations,
                    messages + ["No breaklines were produced."]]

        # build the proposed surface
        surf_id = TinSurface.Create(db, out_surface_name)
        surf = t.GetObject(surf_id, OpenMode.ForWrite)
        surf.BreaklinesDefinition.AddStandardBreaklines(
            breakline_ids, MID_ORDINATE, MAX_DISTANCE, WEEDING_DISTANCE, WEEDING_ANGLE)

        # clip triangulation at the daylight line
        try:
            surf.BoundariesDefinition.AddBoundaries(
                daylight_ids, MID_ORDINATE, SurfaceBoundaryType.Outer, False)
        except:
            messages.append("Outer boundary could not be added; surface built without it.")

        surf.Rebuild()
        t.Commit()

    if failed_stations:
        messages.append("{0} station(s) failed to daylight within {1} units."
                        .format(len(failed_stations), max_search))

    return ["ok", catch_count, failed_stations, messages]


OUT = build()
