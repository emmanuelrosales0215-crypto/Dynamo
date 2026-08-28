# Proposed Surface From Footprint (Dynamo + Civil 3D)

Builds a proposed TIN surface from a pad/site footprint, daylighting out at a design
slope until it catches an existing-ground surface. Runs entirely inside Civil 3D via
the native .NET API from one Python Script node — **no Dynamo packages required**.

Script: [`src/python/proposed_surface_from_footprint.py`](../src/python/proposed_surface_from_footprint.py)

## Why a Python node and not stock nodes

- `Autodesk.Civil.DatabaseServices.Grading` is an **empty stub** in the API — no methods,
  no target, no criteria — in every release 2023 through 2027. Civil 3D's own Grading
  objects cannot be created or configured from code.
- The OOTB Dynamo `FeatureLine` node category first shipped in **2025.1**. On 2024 and
  older there are no stock nodes for this.
- What *is* available in 2024 is the full native API: `TinSurface.Create`,
  `BreaklinesDefinition.AddStandardBreaklines`, `Surface.FindElevationAtXY`,
  `Surface.BoundariesDefinition`.

## Graph wiring

One Python Script node with 8 inputs. All are plain strings and numbers, so they bind
cleanly as Dynamo Player inputs.

| Port | Input | Type | Notes |
|---|---|---|---|
| IN[0] | EG surface name | string | Must match the surface name exactly |
| IN[1] | Footprint layer | string | All curves on this layer are graded |
| IN[2] | Proposed surface name | string | Replaced in place on re-run |
| IN[3] | Cut slope | double | Run:rise — `3.0` means 3:1 |
| IN[4] | Fill slope | double | Run:rise — `4.0` means 4:1 |
| IN[5] | Interval | double | Densification spacing, drawing units |
| IN[6] | Max search | double | Give up daylighting past this distance |
| IN[7] | Design elevation | double or null | `null` uses the footprint's own Z |

Output is `[status, catch_point_count, failed_stations, messages]`. Put a Watch node on it —
`failed_stations` is where a designer finds out which part of the pad never daylighted.

**Set Geometry Scaling to Medium** (Settings → Geometry Scaling). Autodesk documents
null-geometry failures in Civil 3D graphs at Large / Extra Large.

## How the catch points are solved

For each densified station on the footprint:

1. Compute the outward horizontal normal. Interior side comes from the footprint's
   signed area (shoelace), so it works regardless of vertex winding direction.
2. Compare design elevation to EG at the same XY to pick **cut vs fill** — design above
   EG means fill and the slope projects down; below means cut and it projects up.
3. March outward at `interval` steps evaluating `projected_z - eg_z`. On a sign change,
   bisect 40 times to converge on the catch point.

The API also offers `Surface.GetIntersectionPoint(point, vector)`, which ray-casts and
would be faster. It is deliberately **not** used here: its behaviour with a sloped vector
at a surface boundary isn't documented, whereas the sampling solver is verifiable by hand
against a planar surface. Swap it in later if you benchmark it and it holds up.

## Re-running

The script is idempotent. Each run erases the previous proposed surface of the same name
and wipes the `_C3D-AUTO-GRADING` work layer before rebuilding. Without this, Dynamo's
object binding piles up duplicate surfaces on every re-run.

## Known limits

- **Concave corners.** Adjacent daylight rays can cross, producing a self-intersecting
  daylight line and crossing-breakline errors on rebuild. Civil 3D's own grading tool
  has the same problem; Autodesk's workaround is a small fillet at sharp corners. The
  script reports the failure rather than trying to heal it.
- **Off-surface rays.** A ray leaving the EG boundary is reported as a failed station,
  not silently dropped.
- **Untested against a live drawing.** Written from the documented 2024 API surface.
  Verify against a hand-computable case first: on a planar EG at a constant slope, the
  catch point for a given design elevation and side slope can be computed by hand — assert
  the solver matches before trusting it on real topo. Then compare a real pad against the
  same pad built manually with Grading Creation Tools, checking daylight position and
  cut/fill volumes.
