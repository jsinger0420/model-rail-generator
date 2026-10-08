"""Rail cross-section profile definition.

Pure Python (no bpy) so it can be unit-tested and reused outside Blender.

All dimensions are in millimetres at actual model size (the size of the
physical model rail, not the prototype).  Rail "code" is the rail height in
thousandths of an inch, so code 100 = 0.100 in = 2.540 mm.

Profile coordinate system (looking along the rail, from its start end):
    x : lateral, positive to the right, 0 = rail centreline
    z : vertical, 0 = bottom of the rail base
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields, replace

INCH_MM = 25.4


def code_to_height_mm(code: float) -> float:
    """Rail code (thousandths of an inch) -> rail height in mm."""
    return code * INCH_MM / 1000.0


def height_mm_to_code(height_mm: float) -> float:
    """Rail height in mm -> rail code (thousandths of an inch)."""
    return height_mm * 1000.0 / INCH_MM


@dataclass
class RailProfile:
    """Flat-bottom (Vignoles) rail cross-section.

    ::

              head_width
            |<-------->|
         ___.--------.___   ---          ---
        |                |   | head_depth  |
        |____        ____|  ---            |
             |      |                      |
             | web  |  <- web_thickness    | height
         ____|      |____                  |
        /                \\  base_thickness (at web)
       /__________________\\ base_edge_thickness (at flange tip)
       |<-- base_width -->|                ---
    """

    name: str
    height: float
    head_width: float
    head_depth: float
    web_thickness: float
    base_width: float
    base_thickness: float
    base_edge_thickness: float
    head_corner_radius: float = 0.0
    corner_segments: int = 3
    description: str = ""

    # ------------------------------------------------------------------ info
    @property
    def code(self) -> float:
        """Rail code derived from height (thousandths of an inch)."""
        return round(height_mm_to_code(self.height), 1)

    def validate(self) -> list[str]:
        """Return a list of human-readable problems (empty list = valid)."""
        e: list[str] = []
        dims = ("height", "head_width", "head_depth", "web_thickness",
                "base_width", "base_thickness", "base_edge_thickness")
        for f in dims:
            if getattr(self, f) <= 0:
                e.append(f"{f} must be greater than 0")
        if e:
            return e
        if self.head_corner_radius < 0:
            e.append("head_corner_radius cannot be negative")
        if self.corner_segments < 1:
            e.append("corner_segments must be at least 1")
        if self.web_thickness >= self.head_width:
            e.append("web_thickness must be less than head_width")
        if self.web_thickness > self.base_width:
            e.append("web_thickness cannot exceed base_width")
        if self.head_depth + self.base_thickness >= self.height:
            e.append("head_depth + base_thickness must be less than height")
        if self.base_edge_thickness > self.base_thickness:
            e.append("base_edge_thickness cannot exceed base_thickness")
        lim = min(self.head_width / 2.0, self.head_depth)
        if self.head_corner_radius >= lim:
            e.append(f"head_corner_radius must be less than {lim:.3f} mm")
        return e

    def is_valid(self) -> bool:
        return not self.validate()

    # -------------------------------------------------------------- geometry
    def outline(self, cant_deg: float = 0.0) -> list[tuple[float, float]]:
        """Closed outline as (x, z) points, counter-clockwise, no repeat of
        the first point.  ``cant_deg`` tilts the rail about the centre of its
        base (positive tilts the head toward +x)."""
        errs = self.validate()
        if errs:
            raise ValueError(f"Invalid rail profile '{self.name}': " + "; ".join(errs))

        h, hw, hd = self.height, self.head_width, self.head_depth
        wt, bw = self.web_thickness, self.base_width
        bt, bet = self.base_thickness, self.base_edge_thickness
        r = self.head_corner_radius

        right: list[tuple[float, float]] = [
            (bw / 2, 0.0),
            (bw / 2, bet),
            (wt / 2, bt),
            (wt / 2, h - hd),
            (hw / 2, h - hd),
        ]
        if r > 0:
            cx, cz = hw / 2 - r, h - r
            n = max(1, int(self.corner_segments))
            for i in range(n + 1):
                a = (math.pi / 2) * i / n          # 0 -> 90 degrees
                right.append((cx + r * math.cos(a), cz + r * math.sin(a)))
        else:
            right.append((hw / 2, h))

        left = [(-x, z) for (x, z) in reversed(right)]
        pts = _dedupe(right + left)

        if cant_deg:
            t = math.radians(cant_deg)
            c, s = math.cos(t), math.sin(t)
            pts = [(x * c + z * s, -x * s + z * c) for (x, z) in pts]

        if polygon_area(pts) < 0:
            pts.reverse()
        return pts

    def cross_section_area(self) -> float:
        """Area of the cross-section in mm^2."""
        return abs(polygon_area(self.outline()))

    # ------------------------------------------------------- serialisation
    def to_dict(self) -> dict:
        d = asdict(self)
        d["code"] = self.code
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "RailProfile":
        names = {f.name for f in fields(cls)}
        kw = {k: v for k, v in d.items() if k in names}
        if "corner_segments" in kw:
            kw["corner_segments"] = int(kw["corner_segments"])
        for k in kw:
            if k not in ("name", "description", "corner_segments"):
                kw[k] = float(kw[k])
        return cls(**kw)

    def copy(self, **changes) -> "RailProfile":
        return replace(self, **changes)


# ------------------------------------------------------------------ helpers
def polygon_area(pts) -> float:
    """Signed area (positive = counter-clockwise)."""
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def _dedupe(pts, eps=1e-9):
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) <= eps and abs(out[0][1] - out[-1][1]) <= eps:
        out.pop()
    return out


def profile_from_code(code: float, name: str | None = None, description: str = "",
                      **overrides) -> RailProfile:
    """Build a profile for a rail code using typical model-rail proportions.

    Proportions are relative to rail height and are a reasonable starting
    point only; measure your actual rail and override as needed.
    """
    h = code_to_height_mm(code)
    p = RailProfile(
        name=name or f"Code {code:g}",
        height=h,
        head_width=0.46 * h,
        head_depth=0.30 * h,
        web_thickness=0.20 * h,
        base_width=0.88 * h,
        base_thickness=0.17 * h,
        base_edge_thickness=0.08 * h,
        head_corner_radius=0.06 * h,
        corner_segments=3,
        description=description,
    )
    return p.copy(**overrides) if overrides else p
