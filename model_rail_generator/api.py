"""Public API of the Model Rail Generator add-on.

Other add-ons should use only what is listed in ``__all__``; everything else
is internal and may change.  The API follows semantic versioning through
``API_VERSION``: a change in the major number means a breaking change.

Getting hold of the API from another add-on::

    import importlib, sys
    def get_rail_api():
        mod = sys.modules.get("model_rail_api")       # alias set on register
        if mod is None:
            raise RuntimeError("Model Rail Generator add-on is not enabled")
        return mod

    rail = get_rail_api()
    obj = rail.create_rail_object("Code 83", path={"kind": "ARC", "radius": 457.2,
                                                   "angle": 30, "direction": "LEFT"})

Units: every length in this API is millimetres at actual model size.
Conversion to Blender scene units happens only when objects are created or
read (see ``mm_to_blender_units``).
"""

from __future__ import annotations

import json
import math
import os

from .exporters import FORMATS, export_mesh
from .geometry import (MeshData, PathPoint, RailPath, arc_path, build_rail,
                       polyline_path, straight_path)
from .presets import BUILTIN_PRESETS, PresetError, PresetLibrary
from .profile import (RailProfile, code_to_height_mm, height_mm_to_code,
                      profile_from_code)

API_VERSION = (1, 0, 0)

#: Custom property key under which rail parameters are stored on objects.
RAIL_PROP_KEY = "model_rail"

__all__ = [
    "API_VERSION", "RAIL_PROP_KEY", "FORMATS",
    # data types
    "RailProfile", "RailPath", "PathPoint", "MeshData", "PresetError",
    # unit helpers
    "code_to_height_mm", "height_mm_to_code", "mm_to_blender_units",
    # presets
    "list_presets", "list_builtin_presets", "list_user_presets", "get_preset",
    "save_preset", "delete_preset", "is_builtin_preset", "profile_from_code",
    "get_preset_file", "set_preset_file", "import_presets", "export_presets",
    # geometry (no bpy needed)
    "make_path", "straight_path", "arc_path", "polyline_path",
    "resolve_profile", "generate_rail_mesh",
    # blender objects
    "create_rail_object", "create_rail_along_curve", "rebuild_rail_object",
    "is_rail_object", "get_rail_params", "object_to_mesh_data",
    # export
    "export_rail",
]


# ================================================================ presets
_library: PresetLibrary | None = None
_preset_file_override: str | None = None


def _default_preset_file() -> str:
    """Path of the user preset file: $MODEL_RAIL_PRESETS, Blender's config folder, or ~/.model_rail_generator."""
    env = os.environ.get("MODEL_RAIL_PRESETS")
    if env:
        return env
    try:
        import bpy
        d = bpy.utils.user_resource('CONFIG', path="model_rail_generator", create=True)
    except Exception:
        d = os.path.join(os.path.expanduser("~"), ".model_rail_generator")
    return os.path.join(d, "rail_presets.json")


def _lib() -> PresetLibrary:
    """The shared PresetLibrary, created on first use."""
    global _library
    if _library is None:
        _library = PresetLibrary(_preset_file_override or _default_preset_file())
    return _library


def get_preset_file() -> str:
    """Path of the JSON file that stores user presets."""
    return _lib().user_file


def set_preset_file(path: str | None) -> None:
    """Use a different user preset file (``None`` restores the default)."""
    global _library, _preset_file_override
    _preset_file_override = path
    _library = None


def list_presets() -> list[str]:
    """All preset names: built-ins (largest rail first) then user presets."""
    return _lib().names()


def list_builtin_presets() -> list[str]:
    """Names of the built-in presets, largest rail first."""
    return _lib().builtin_names()


def list_user_presets() -> list[str]:
    """Names of the user's saved presets, sorted alphabetically."""
    return _lib().user_names()


def is_builtin_preset(name: str) -> bool:
    """True if ``name`` is a built-in (read-only) preset."""
    return name in BUILTIN_PRESETS


def get_preset(name: str) -> RailProfile:
    """Return a copy of the named preset. Raises ``KeyError`` if missing."""
    return _lib().get(name)


def save_preset(profile: RailProfile, overwrite: bool = True) -> None:
    """Save a user preset under ``profile.name``. Raises ``PresetError``."""
    _lib().save(profile, overwrite)


def delete_preset(name: str) -> None:
    """Delete a user preset. Built-ins cannot be deleted (``PresetError``)."""
    _lib().delete(name)


def import_presets(path: str, overwrite: bool = True) -> list[str]:
    """Merge presets from a JSON file into the user presets; returns the names imported."""
    return _lib().import_json(path, overwrite)


def export_presets(path: str, names: list[str] | None = None) -> None:
    """Write user presets (or just ``names``) to a JSON file for sharing."""
    _lib().export_json(path, names)


def resolve_profile(profile) -> RailProfile:
    """Accept a ``RailProfile``, a preset name, a rail code number or a dict."""
    if isinstance(profile, RailProfile):
        return profile
    if isinstance(profile, str):
        return get_preset(profile)
    if isinstance(profile, (int, float)):
        return profile_from_code(profile)
    if isinstance(profile, dict):
        return RailProfile.from_dict(profile)
    raise TypeError(f"Cannot interpret {profile!r} as a rail profile")


# =============================================================== geometry
def make_path(spec) -> RailPath:
    """Build a path from a dict spec (or return a ``RailPath`` unchanged).

    Specs (lengths in mm, angles in degrees)::

        {"kind": "STRAIGHT", "length": 300}
        {"kind": "ARC", "radius": 457.2, "angle": 30, "direction": "LEFT",
         "max_segment_angle": 1.0, "segments": None, "chord_tolerance": None}
        {"kind": "POLYLINE", "points": [(x, y, z), ...], "closed": False}
    """
    if isinstance(spec, RailPath):
        return spec
    if not isinstance(spec, dict):
        raise TypeError("path must be a RailPath or a dict spec")
    kind = spec.get("kind", "STRAIGHT").upper()
    if kind == "STRAIGHT":
        return straight_path(float(spec["length"]))
    if kind == "ARC":
        return arc_path(float(spec["radius"]), float(spec["angle"]),
                        spec.get("direction", "LEFT"), spec.get("segments"),
                        float(spec.get("max_segment_angle", 1.0)),
                        spec.get("chord_tolerance"))
    if kind == "POLYLINE":
        return polyline_path(spec["points"], bool(spec.get("closed", False)))
    raise ValueError(f"Unknown path kind '{kind}'")


def generate_rail_mesh(profile, path, lateral_offset: float = 0.0,
                       cant_deg: float = 0.0, cap_ends: bool = True) -> MeshData:
    """Pure geometry: closed, outward-facing rail mesh in millimetres.

    ``profile``: RailProfile | preset name | rail code | dict
    ``path``: RailPath | dict spec (see ``make_path``)
    ``lateral_offset``: shift right of the path centreline (mm). Two calls
        with +/- gauge/2 give the two rails of a track on a shared centreline.
    ``cant_deg``: tilt of the rail (positive leans the head toward +x).
    Works without Blender.
    """
    return build_rail(resolve_profile(profile), make_path(path),
                      lateral_offset, cant_deg, cap_ends)


# ========================================================= blender helpers
def mm_to_blender_units(scene=None) -> float:
    """Factor that converts millimetres to Blender units for ``scene``.

    Uses the current scene when ``scene`` is None. 1 BU = 1 m at Unit Scale
    1.0, so the default factor is 0.001.
    """
    import bpy
    scene = scene or bpy.context.scene
    scale = scene.unit_settings.scale_length if scene else 1.0
    return 0.001 / (scale or 1.0)


def _store_params(obj, profile: RailProfile, path_spec, lateral_offset, cant_deg, cap_ends):
    """Save the generation parameters on ``obj`` so it can be rebuilt or inspected later."""
    obj[RAIL_PROP_KEY] = json.dumps({
        "api_version": list(API_VERSION),
        "profile": profile.to_dict(),
        "path": path_spec,
        "lateral_offset": lateral_offset,
        "cant_deg": cant_deg,
        "cap_ends": cap_ends,
    })
    obj["rail_code"] = profile.code


def _mesh_from_data(name: str, md: MeshData, factor: float):
    """Create a Blender mesh named ``name`` from mm MeshData, scaled by ``factor``."""
    import bpy
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x * factor, y * factor, z * factor) for x, y, z in md.vertices],
                   [], md.faces)
    me.validate(clean_customdata=False)
    me.update()
    return me


def _path_spec_for_storage(path):
    """Turn a path spec or RailPath into a JSON-safe dict for storing on an object."""
    if isinstance(path, dict):
        return dict(path)
    return {"kind": "POLYLINE", "points": [list(p.position) for p in path.points],
            "closed": path.closed}


def create_rail_object(profile, path, name: str | None = None, collection=None,
                       location=(0.0, 0.0, 0.0), rotation_z_deg: float = 0.0,
                       lateral_offset: float = 0.0, cant_deg: float = 0.0,
                       cap_ends: bool = True, scene=None):
    """Create a rail mesh object and return it.

    The object is linked to ``collection`` (default: the active collection).
    ``location`` is in Blender units. Generation parameters are stored on the
    object (see ``get_rail_params``) so it can be rebuilt later.
    """
    import bpy
    prof = resolve_profile(profile)
    md = generate_rail_mesh(prof, path, lateral_offset, cant_deg, cap_ends)
    scene = scene or bpy.context.scene
    name = name or f"Rail {prof.name}"
    me = _mesh_from_data(name, md, mm_to_blender_units(scene))
    obj = bpy.data.objects.new(name, me)
    obj.location = location
    obj.rotation_euler = (0.0, 0.0, math.radians(rotation_z_deg))
    (collection or bpy.context.collection).objects.link(obj)
    _store_params(obj, prof, _path_spec_for_storage(path), lateral_offset, cant_deg, cap_ends)
    return obj


def _curve_points_mm(curve_obj, scene=None):
    """Ordered world-space points (mm) of a curve object's first spline."""
    import bpy
    dg = bpy.context.evaluated_depsgraph_get()
    ev = curve_obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        if not me.vertices:
            raise ValueError(f"Curve '{curve_obj.name}' produced no geometry")
        adj: dict[int, list[int]] = {}
        for e in me.edges:
            a, b = e.vertices
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)
        if not adj:
            raise ValueError("Curve must not have bevel/extrude; remove them to use as a path")
        if any(len(v) > 2 for v in adj.values()):
            raise ValueError("Curve has branches or a bevel; use a single plain spline")
        ends = [v for v, n in adj.items() if len(n) == 1]
        closed = not ends
        start = ends[0] if ends else next(iter(adj))
        order, prev, cur = [start], None, start
        while True:
            nxt = [n for n in adj[cur] if n != prev]
            if not nxt or nxt[0] == start:
                break
            prev, cur = cur, nxt[0]
            order.append(cur)
        mw = curve_obj.matrix_world
        f = 1.0 / mm_to_blender_units(scene)
        pts = [tuple(c * f for c in (mw @ me.vertices[i].co)) for i in order]
        return pts, closed
    finally:
        ev.to_mesh_clear()


def create_rail_along_curve(curve_obj, profile, name: str | None = None, collection=None,
                            lateral_offset: float = 0.0, cant_deg: float = 0.0,
                            cap_ends: bool = True, scene=None):
    """Sweep a rail along a Blender curve object and return the new object.

    Uses the curve's first spline in world space. Raise the curve's
    resolution for smoother rail.
    """
    import bpy
    pts, closed = _curve_points_mm(curve_obj, scene)
    spec = {"kind": "POLYLINE", "points": [list(p) for p in pts], "closed": closed}
    obj = create_rail_object(profile, spec, name or f"Rail {curve_obj.name}", collection,
                             lateral_offset=lateral_offset, cant_deg=cant_deg,
                             cap_ends=cap_ends, scene=scene)
    params = json.loads(obj[RAIL_PROP_KEY])
    params["source_curve"] = curve_obj.name
    obj[RAIL_PROP_KEY] = json.dumps(params)
    return obj


def is_rail_object(obj) -> bool:
    """True if ``obj`` was made by this add-on (it carries rail parameters)."""
    return obj is not None and RAIL_PROP_KEY in obj.keys()


def get_rail_params(obj) -> dict:
    """Parameters the rail was generated with (``profile`` is a dict)."""
    if not is_rail_object(obj):
        raise ValueError(f"'{getattr(obj, 'name', obj)}' is not a rail object")
    return json.loads(obj[RAIL_PROP_KEY])


def rebuild_rail_object(obj, profile=None, path=None, lateral_offset=None,
                        cant_deg=None, cap_ends=None, scene=None):
    """Regenerate a rail object's mesh, changing only the parameters given.

    Keeps the object, its transform, modifiers and materials.
    """
    import bpy
    p = get_rail_params(obj)
    prof = resolve_profile(profile if profile is not None else p["profile"])
    path_spec = path if path is not None else p["path"]
    lo = p["lateral_offset"] if lateral_offset is None else lateral_offset
    cd = p["cant_deg"] if cant_deg is None else cant_deg
    ce = p["cap_ends"] if cap_ends is None else cap_ends
    md = generate_rail_mesh(prof, path_spec, lo, cd, ce)
    old = obj.data
    new = _mesh_from_data(old.name, md, mm_to_blender_units(scene))
    for mat in old.materials:
        new.materials.append(mat)
    obj.data = new
    if old.users == 0:
        bpy.data.meshes.remove(old)
    _store_params(obj, prof, _path_spec_for_storage(path_spec), lo, cd, ce)
    return obj


def object_to_mesh_data(obj, apply_transform: bool = True, scene=None) -> MeshData:
    """Evaluated (modifiers applied) mesh of ``obj`` as triangles in mm."""
    import bpy
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        me.calc_loop_triangles()
        f = 1.0 / mm_to_blender_units(scene)
        mw = obj.matrix_world if apply_transform else None
        verts = []
        for v in me.vertices:
            co = mw @ v.co if mw is not None else v.co
            verts.append((co.x * f, co.y * f, co.z * f))
        faces = [tuple(t.vertices) for t in me.loop_triangles]
        if mw is not None and mw.determinant() < 0:
            faces = [tuple(reversed(t)) for t in faces]
        return MeshData(verts, faces)
    finally:
        ev.to_mesh_clear()


def _merge(meshes) -> MeshData:
    """Combine several MeshData into one, renumbering the face indices."""
    out = MeshData()
    for md in meshes:
        base = len(out.vertices)
        out.vertices.extend(md.vertices)
        out.faces.extend(tuple(i + base for i in f) for f in md.faces)
    return out


def export_rail(target, filepath: str, fmt: str | None = None, name: str | None = None) -> str:
    """Export to STL/OBJ in millimetres.

    ``target``: MeshData, a Blender object, or a list of objects (merged into
    one file, world transforms applied). ``fmt``: "STL" (binary),
    "STL_ASCII" or "OBJ"; inferred from the extension when omitted.
    Returns the path written.
    """
    if isinstance(target, MeshData):
        md, label = target, name or "rail"
    else:
        objs = list(target) if isinstance(target, (list, tuple)) else [target]
        if not objs:
            raise ValueError("Nothing to export")
        md = _merge(object_to_mesh_data(o) for o in objs)
        label = name or objs[0].name
    if filepath.startswith("//"):
        import bpy
        filepath = bpy.path.abspath(filepath)
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    return export_mesh(filepath, md, fmt, label)
