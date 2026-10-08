"""STL / OBJ writers.  Pure Python (no bpy) so output is identical across
Blender versions and the API works headless.  Units are millimetres, which is
what slicers expect."""

from __future__ import annotations

import math
import os
import struct

from .geometry import MeshData

FORMATS = ("STL", "STL_ASCII", "OBJ")


def _normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    L = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return nx / L, ny / L, nz / L


def write_stl(path: str, mesh: MeshData, binary: bool = True, name: str = "rail") -> str:
    v = mesh.vertices
    tris = mesh.triangles()
    if binary:
        with open(path, "wb") as fh:
            header = f"Model Rail Generator: {name} (mm)".encode("ascii", "replace")[:80]
            fh.write(header.ljust(80, b" "))
            fh.write(struct.pack("<I", len(tris)))
            for a, b, c in tris:
                fh.write(struct.pack("<12fH", *_normal(v[a], v[b], v[c]),
                                     *v[a], *v[b], *v[c], 0))
    else:
        safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in name)
        with open(path, "w", encoding="ascii") as fh:
            fh.write(f"solid {safe}\n")
            for a, b, c in tris:
                n = _normal(v[a], v[b], v[c])
                fh.write(f"  facet normal {n[0]:e} {n[1]:e} {n[2]:e}\n    outer loop\n")
                for p in (v[a], v[b], v[c]):
                    fh.write(f"      vertex {p[0]:e} {p[1]:e} {p[2]:e}\n")
                fh.write("    endloop\n  endfacet\n")
            fh.write(f"endsolid {safe}\n")
    return path


def write_obj(path: str, mesh: MeshData, name: str = "rail") -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# Model Rail Generator - units: millimetres\n")
        fh.write(f"o {name}\n")
        for x, y, z in mesh.vertices:
            fh.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for f in mesh.faces:
            fh.write("f " + " ".join(str(i + 1) for i in f) + "\n")
    return path


def export_mesh(path: str, mesh: MeshData, fmt: str | None = None, name: str = "rail") -> str:
    """Write ``mesh`` (mm).  ``fmt`` is one of FORMATS; if omitted it is
    inferred from the file extension (.stl -> binary STL, .obj -> OBJ)."""
    if fmt is None:
        ext = os.path.splitext(path)[1].lower()
        fmt = {".stl": "STL", ".obj": "OBJ"}.get(ext)
        if fmt is None:
            raise ValueError("Cannot infer export format; use a .stl or .obj extension")
    fmt = fmt.upper()
    if fmt == "STL":
        return write_stl(path, mesh, True, name)
    if fmt == "STL_ASCII":
        return write_stl(path, mesh, False, name)
    if fmt == "OBJ":
        return write_obj(path, mesh, name)
    raise ValueError(f"Unknown export format '{fmt}'; expected one of {FORMATS}")
