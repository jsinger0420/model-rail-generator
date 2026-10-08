# Model Rail Generator (Blender add-on)

Generates straight, curved or curve-following lengths of model railroad rail as
closed, manifold meshes ready for 3D printing, and exports them to STL or OBJ in
millimetres. Rail profiles come from built-in "code" presets or from dimensions
you enter and save as your own presets. A public Python API lets other add-ons
(track, turnout, or layout generators) build rail the same way.

Tested with Blender 5.2 (headless); targets Blender 3.6 and later.

## Install

The ready-to-install zip is in `dist/` (rebuild it with `python build.py` after changing the code), then:

* **Blender 4.2+**: Edit > Preferences > Get Extensions > ▾ menu > *Install from Disk…* and pick
  the zip.
* **Blender 3.6–4.1**: Edit > Preferences > Add-ons > *Install…* and pick the same zip.

The panel appears in the 3D Viewport sidebar (N) under the **Rail** tab.

## Using the panel

1. **Profile** – choose a preset, or edit any dimension. All dimensions are millimetres at
   actual model size. The panel shows the resulting rail code. *Fill From Code* fills every
   dimension with typical proportions for any code you type (e.g. 65).
2. **Save Preset** – enter a name and click *Save Preset*. Built-in presets are read-only, so
   give your measured rail a new name (e.g. "Peco Code 75 measured"). User presets are stored
   in `<Blender config>/model_rail_generator/rail_presets.json` and survive add-on updates.
3. **Shape** – *Straight* (length), *Curved* (radius to rail centreline, angle, left/right), or
   *Along Curve* (any curve object; raise its resolution for smoother rail). Length/radius/offset
   can be entered in mm or inches. *Offset* shifts the rail sideways, *Cant* tilts it.
4. **Generate Rail** creates the object at the 3D cursor. *Update Selected Rails* regenerates
   selected rails with the current settings (materials, transform and modifiers are kept).
5. **Export** writes selected objects (merged, transforms and modifiers applied) to binary STL,
   ASCII STL or OBJ in millimetres. With nothing selected it exports a rail built from the
   current settings.

## Built-in presets

Height is exact (code ÷ 1000 inch). Other dimensions use typical model-rail proportions
(head 0.46 H, head depth 0.30 H, web 0.20 H, base 0.88 H, base 0.17 H at web / 0.08 H at
edge, head corner radius 0.06 H). Rail differs between manufacturers, so for an exact match
measure your rail with calipers and save a custom preset.

| Preset | Height mm | Typical use |
|---|---|---|
| Code 332 | 8.433 | G scale (LGB, Aristo, USA Trains) |
| Code 250 | 6.350 | G / Fn3 fine scale |
| Code 215 | 5.461 | O scale heavy rail |
| Code 148 | 3.759 | O scale (Atlas O) |
| Code 125 | 3.175 | O 2-rail, S hi-rail |
| Code 100 | 2.540 | HO standard |
| Code 83  | 2.108 | HO mainline |
| Code 80  | 2.032 | N standard |
| Code 70  | 1.778 | HO branchline, S fine scale, On30 |
| Code 55  | 1.397 | N fine scale |
| Code 40  | 1.016 | N/HO light rail, Z |

## Geometry conventions

* Units: millimetres in the API and in exported files. Objects in Blender are converted to
  scene units (1 mm = 0.001 BU at Unit Scale 1.0; 1 mm = 1 BU at Unit Scale 0.001).
* A rail starts at its local origin and runs along +Y; Z is up; the base sits on Z = 0.
* Profile x = 0 is the rail centreline. Arc radius is measured to that centreline.
* *Left/Right* curves turn left/right as seen travelling along +Y.
* Positive `lateral_offset` is to the right of travel, so on a left-hand curve it increases
  the radius. Building HO track (16.5 mm gauge) on one centreline:
  `lateral_offset = ±(16.5/2 + head_width/2)` (gauge is measured between the inside faces
  of the railheads).
* Meshes are closed and outward-facing (tested manifold, positive volume). Full 360° arcs and
  cyclic curves produce closed rings without end caps.

## Public API

While the add-on is enabled its API module is registered as **`model_rail_api`**, so other
add-ons don't need to know the install path:

```python
import sys

def get_rail_api(min_version=(1, 0, 0)):
    api = sys.modules.get("model_rail_api")
    if api is None:
        raise RuntimeError("Enable the 'Model Rail Generator' add-on")
    if api.API_VERSION[0] != min_version[0] or api.API_VERSION < min_version:
        raise RuntimeError(f"Need Model Rail API {min_version}, found {api.API_VERSION}")
    return api
```

`API_VERSION` follows semantic versioning; only names in `api.__all__` are public.
Anything that needs no Blender object (profiles, presets, geometry, export of `MeshData`)
also works outside Blender.

### Profiles and presets

| Function | Description |
|---|---|
| `RailProfile(name, height, head_width, head_depth, web_thickness, base_width, base_thickness, base_edge_thickness, head_corner_radius=0, corner_segments=3, description="")` | Dataclass. `.code`, `.validate()` → list of problems, `.outline(cant_deg=0)` → CCW (x, z) points, `.cross_section_area()`, `.to_dict()`, `.from_dict()`, `.copy(**changes)` |
| `profile_from_code(code, name=None, description="", **overrides)` | Profile with typical proportions for any code |
| `code_to_height_mm(code)`, `height_mm_to_code(mm)` | Unit helpers |
| `list_presets()`, `list_builtin_presets()`, `list_user_presets()` | Preset names |
| `get_preset(name)` | Copy of a preset (`KeyError` if missing) |
| `save_preset(profile, overwrite=True)` | Save a user preset (`PresetError` for built-in names or invalid dims) |
| `delete_preset(name)` | Delete a user preset |
| `import_presets(path)`, `export_presets(path, names=None)` | Share presets as JSON |
| `get_preset_file()`, `set_preset_file(path)` | Where user presets live |
| `resolve_profile(x)` | Accepts a `RailProfile`, preset name, code number or dict |

### Paths and meshes (pure Python)

| Function | Description |
|---|---|
| `make_path(spec)` | `{"kind": "STRAIGHT", "length"}`, `{"kind": "ARC", "radius", "angle", "direction", "max_segment_angle", "segments", "chord_tolerance"}`, `{"kind": "POLYLINE", "points", "closed"}` |
| `straight_path`, `arc_path`, `polyline_path` | Same, as functions returning `RailPath` |
| `generate_rail_mesh(profile, path, lateral_offset=0, cant_deg=0, cap_ends=True)` | → `MeshData` (mm) with `.vertices`, `.faces`, `.triangles()`, `.volume()`, `.bounds()`, `.is_manifold()`, `.transformed()` |

### Blender objects

| Function | Description |
|---|---|
| `create_rail_object(profile, path, name=None, collection=None, location=(0,0,0), rotation_z_deg=0, lateral_offset=0, cant_deg=0, cap_ends=True)` | Creates and links a mesh object; `location` in Blender units |
| `create_rail_along_curve(curve_obj, profile, ...)` | Sweeps along a curve object's first spline (world space) |
| `rebuild_rail_object(obj, profile=None, path=None, ...)` | Regenerate in place, changing only what you pass |
| `is_rail_object(obj)`, `get_rail_params(obj)` | Parameters are stored as JSON in `obj["model_rail"]`; `obj["rail_code"]` holds the code |
| `object_to_mesh_data(obj, apply_transform=True)` | Evaluated mesh in mm |
| `mm_to_blender_units(scene=None)` | Conversion factor |
| `export_rail(target, filepath, fmt=None, name=None)` | `target` = `MeshData`, object or list of objects; `fmt` = `"STL"`, `"STL_ASCII"`, `"OBJ"` (or from extension) |

### Example: a 30° piece of HO code 83 track

```python
rail = get_rail_api()
prof = rail.get_preset("Code 83")
half = 16.5 / 2 + prof.head_width / 2
arc = {"kind": "ARC", "radius": 457.2, "angle": 30, "direction": "LEFT"}  # 18" radius
rails = [rail.create_rail_object(prof, arc, name=f"Rail {side}", lateral_offset=off)
         for side, off in (("inner", -half), ("outer", half))]
rail.export_rail(rails, "//track_18in_30deg.stl")
```

## Development

Repository layout:

```
RAIL/
├── model_rail_generator/   the add-on package (this folder is what goes in the zip)
├── tests/
│   ├── test_core.py        geometry, presets, export — plain Python, no Blender needed
│   └── test_blender.py     UI operators + API inside Blender
├── build.py                makes dist/model_rail_generator-<version>.zip
├── dist/                   installable add-on zip(s)
└── README.md
```

Run the tests from the repository folder:

```
python tests/test_core.py
"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" -b --factory-startup --python tests/test_blender.py
```

(`pip install bpy` also lets `python tests/test_blender.py` run without opening Blender.)

To edit code and see changes in Blender without reinstalling, link the package into Blender's
add-on folder once (Command Prompt, adjust the Blender version):

```
mklink /J "%APPDATA%\Blender Foundation\Blender\4.2\scripts\addons\model_rail_generator" "C:\Users\Jsing\BLENDERWORKBENCHES\RAIL\model_rail_generator"
```

Then enable it under Add-ons and use *Reload Scripts* (F3 > Reload Scripts) after edits.
When releasing, bump the version in both `blender_manifest.toml` and `bl_info` in
`__init__.py`, and bump `API_VERSION` in `api.py` if the public API changed.

## Files

| File | Contents |
|---|---|
| `profile.py` | `RailProfile`, outline generation, code conversion |
| `presets.py` | Built-in presets, JSON user preset library |
| `geometry.py` | Paths, sweep, triangulation, `MeshData` |
| `exporters.py` | STL / OBJ writers (no bpy) |
| `api.py` | Public API |
| `ui.py` | Sidebar panel, operators, scene properties |
