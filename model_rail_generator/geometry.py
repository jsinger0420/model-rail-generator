"""Path generation and profile sweeping.  Pure Python (no bpy).

Units are millimetres.  Paths lie in the XY plane by default (Z up); a rail
starts at the origin heading +Y unless a custom polyline is supplied.  The
rail cross-section always stays upright (perpendicular to the horizontal
direction of travel), which is what you want for model track even on grades.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .profile import RailProfile, polygon_area

Vec3 = tuple[float, float, float]


# =================================================================== paths
@dataclass
class PathPoint:
    """One point on a sweep path: position (mm), horizontal direction of travel and corner miter."""
    position: Vec3
    tangent: tuple[float, float]   # horizontal unit direction of travel (x, y)
    miter: float = 1.0             # lateral stretch at polyline corners


@dataclass
class RailPath:
    """Ordered points the rail profile is swept along; ``closed`` joins the last point to the first."""
    points: list[PathPoint]
    closed: bool = False

    def length(self) -> float:
        """Total length of the path in millimetres."""
        pts = [p.position for p in self.points]
        if self.closed:
            pts = pts + [pts[0]]
        return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def straight_path(length: float) -> RailPath:
    """Straight rail of ``length`` mm from the origin along +Y."""
    if length <= 0:
        raise ValueError("length must be greater than 0")
    t = (0.0, 1.0)
    return RailPath([PathPoint((0.0, 0.0, 0.0), t), PathPoint((0.0, length, 0.0), t)])


def arc_segment_count(radius: float, angle_deg: float, max_segment_angle_deg: float = 1.0,
                      chord_tolerance: float | None = None) -> int:
    """Number of straight segments used to approximate an arc."""
    seg = max_segment_angle_deg
    if chord_tolerance and chord_tolerance > 0 and chord_tolerance < radius:
        seg = min(seg, math.degrees(2 * math.acos(1 - chord_tolerance / radius)))
    return max(1, math.ceil(abs(angle_deg) / max(seg, 1e-6)))


def arc_path(radius: float, angle_deg: float, direction: str = "LEFT",
             segments: int | None = None, max_segment_angle_deg: float = 1.0,
             chord_tolerance: float | None = None) -> RailPath:
    """Circular curve starting at the origin heading +Y.

    ``radius`` is measured to the rail centreline (profile x = 0).
    ``direction`` is ``"LEFT"`` or ``"RIGHT"`` (as seen travelling along +Y).
    """
    if radius <= 0:
        raise ValueError("radius must be greater than 0")
    if not 0 < angle_deg <= 360:
        raise ValueError("angle must be in (0, 360] degrees")
    direction = direction.upper()
    if direction not in ("LEFT", "RIGHT"):
        raise ValueError("direction must be 'LEFT' or 'RIGHT'")

    n = segments or arc_segment_count(radius, angle_deg, max_segment_angle_deg, chord_tolerance)
    full = abs(angle_deg - 360) < 1e-9
    total = math.radians(angle_deg)
    count = n if full else n + 1
    sgn = -1.0 if direction == "LEFT" else 1.0
    pts = []
    for i in range(count):
        a = total * i / n
        x = sgn * (radius - radius * math.cos(a))
        y = radius * math.sin(a)
        pts.append(PathPoint((x, y, 0.0), (sgn * math.sin(a), math.cos(a))))
    return RailPath(pts, closed=full)


def polyline_path(points, closed: bool = False) -> RailPath:
    """Sweep path through arbitrary 3D points (mm), e.g. from a Blender curve.

    Corner tangents are the bisector of the adjoining segments and the
    profile is widened by a miter factor so the rail keeps a constant width.
    """
    pts = [tuple(map(float, p)) + (0.0,) * (3 - len(p)) for p in points]
    # drop consecutive duplicates
    clean = [pts[0]]
    for p in pts[1:]:
        if math.dist(p[:2], clean[-1][:2]) > 1e-9:
            clean.append(p)
    if closed and len(clean) > 2 and math.dist(clean[0][:2], clean[-1][:2]) <= 1e-9:
        clean.pop()
    if len(clean) < 2:
        raise ValueError("a path needs at least two distinct points")

    def seg_dir(a, b):
        """Horizontal unit direction from point ``a`` to point ``b``."""
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        return (dx / L, dy / L)

    n = len(clean)
    out = []
    for i, p in enumerate(clean):
        prev_d = next_d = None
        if i > 0 or closed:
            prev_d = seg_dir(clean[i - 1], p)
        if i < n - 1 or closed:
            next_d = seg_dir(p, clean[(i + 1) % n])
        if prev_d and next_d:
            tx, ty = prev_d[0] + next_d[0], prev_d[1] + next_d[1]
            L = math.hypot(tx, ty)
            if L < 1e-9:                      # 180 degree reversal
                t, miter = next_d, 1.0
            else:
                t = (tx / L, ty / L)
                cos_half = t[0] * next_d[0] + t[1] * next_d[1]
                miter = 1.0 / max(cos_half, 0.2)
        else:
            t, miter = (prev_d or next_d), 1.0
        out.append(PathPoint(p, t, miter))
    return RailPath(out, closed=closed)


# ==================================================================== mesh
@dataclass
class MeshData:
    """Simple indexed mesh in millimetres.

    Faces are tris and quads with outward-facing (counter-clockwise) winding,
    and the solid is closed.
    """
    vertices: list[Vec3] = field(default_factory=list)
    faces: list[tuple[int, ...]] = field(default_factory=list)

    def triangles(self) -> list[tuple[int, int, int]]:
        """Faces split into triangles (quads become two triangles)."""
        tris = []
        for f in self.faces:
            for i in range(1, len(f) - 1):
                tris.append((f[0], f[i], f[i + 1]))
        return tris

    def volume(self) -> float:
        """Signed volume in mm^3 (positive when normals face outward)."""
        v = self.vertices
        s = 0.0
        for a, b, c in self.triangles():
            ax, ay, az = v[a]; bx, by, bz = v[b]; cx, cy, cz = v[c]
            s += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
        return s / 6.0

    def bounds(self) -> tuple[Vec3, Vec3]:
        """Bounding box as ((min x, y, z), (max x, y, z)) in millimetres."""
        xs, ys, zs = zip(*self.vertices)
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    def is_manifold(self) -> bool:
        """Every edge shared by exactly two faces in opposite directions."""
        edges: dict[tuple[int, int], int] = {}
        for f in self.faces:
            for i in range(len(f)):
                e = (f[i], f[(i + 1) % len(f)])
                edges[e] = edges.get(e, 0) + 1
        return all(c == 1 and edges.get((b, a)) == 1 for (a, b), c in edges.items())

    def transformed(self, scale: float = 1.0, offset: Vec3 = (0.0, 0.0, 0.0)) -> "MeshData":
        """Copy of the mesh scaled by ``scale`` and then moved by ``offset``."""
        ox, oy, oz = offset
        return MeshData([(x * scale + ox, y * scale + oy, z * scale + oz) for x, y, z in self.vertices],
                        list(self.faces))


def sweep_profile(outline, path: RailPath, lateral_offset: float = 0.0,
                  cap_ends: bool = True) -> MeshData:
    """Sweep a CCW (x, z) outline along ``path``.

    ``lateral_offset`` shifts the rail sideways (positive = right of travel),
    useful for building the two rails of a track from one centreline.
    """
    if polygon_area(outline) < 0:
        outline = list(reversed(outline))
    m = len(outline)
    pts = path.points
    verts: list[Vec3] = []
    for pp in pts:
        px, py, pz = pp.position
        tx, ty = pp.tangent
        rx, ry = ty, -tx                     # right-hand normal (horizontal)
        for x, z in outline:
            lx = (x + lateral_offset) * pp.miter
            verts.append((px + rx * lx, py + ry * lx, pz + z))

    faces: list[tuple[int, ...]] = []
    rings = len(pts)
    spans = rings if path.closed else rings - 1
    for k in range(spans):
        a0 = k * m
        a1 = ((k + 1) % rings) * m
        for i in range(m):
            j = (i + 1) % m
            faces.append((a0 + i, a1 + i, a1 + j, a0 + j))

    if cap_ends and not path.closed:
        tris = triangulate_polygon(outline)
        last = (rings - 1) * m
        for a, b, c in tris:
            faces.append((a, b, c))                       # start cap faces -forward
            faces.append((last + c, last + b, last + a))  # end cap faces +forward

    md = MeshData(verts, faces)
    if md.volume() < 0:                       # e.g. mirrored polyline input
        md.faces = [tuple(reversed(f)) for f in md.faces]
    return md


def build_rail(profile: RailProfile, path: RailPath, lateral_offset: float = 0.0,
               cant_deg: float = 0.0, cap_ends: bool = True) -> MeshData:
    """Convenience: profile + path -> closed rail mesh (mm)."""
    return sweep_profile(profile.outline(cant_deg), path, lateral_offset, cap_ends)


# ========================================================== triangulation
def triangulate_polygon(pts) -> list[tuple[int, int, int]]:
    """Triangulate a simple 2D polygon by ear clipping.

    Returns counter-clockwise index triples into ``pts``.
    """
    n = len(pts)
    idx = list(range(n))
    if polygon_area(pts) < 0:
        idx.reverse()

    def cross(o, a, b):
        """Z of the cross product of o->a and o->b (positive when a-b turns left)."""
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def inside(p, a, b, c):
        """True if point ``p`` lies inside or on triangle a-b-c."""
        return cross(a, b, p) >= -1e-12 and cross(b, c, p) >= -1e-12 and cross(c, a, p) >= -1e-12

    tris = []
    guard = 0
    while len(idx) > 3 and guard < 10 * n * n:
        guard += 1
        L = len(idx)
        clipped = False
        for i in range(L):
            a, b, c = idx[i - 1], idx[i], idx[(i + 1) % L]
            cr = cross(pts[a], pts[b], pts[c])
            if cr <= 1e-12:
                continue
            if any(inside(pts[o], pts[a], pts[b], pts[c])
                   for o in idx if o not in (a, b, c)
                   and pts[o] not in (pts[a], pts[b], pts[c])):
                continue
            tris.append((a, b, c))
            idx.pop(i)
            clipped = True
            break
        if not clipped:
            # remove a collinear vertex, or give up and fan the remainder
            for i in range(L):
                a, b, c = idx[i - 1], idx[i], idx[(i + 1) % L]
                if abs(cross(pts[a], pts[b], pts[c])) <= 1e-12:
                    idx.pop(i)
                    break
            else:
                break
    if len(idx) == 3:
        tris.append(tuple(idx))
    elif len(idx) > 3:
        tris.extend((idx[0], idx[i], idx[i + 1]) for i in range(1, len(idx) - 1))
    return tris
