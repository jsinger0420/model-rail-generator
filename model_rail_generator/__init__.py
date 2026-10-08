"""Model Rail Generator — Blender add-on.

Generates straight, curved or curve-following lengths of model railroad rail
from a cross-section profile (built-in "code" presets or user dimensions),
and exports them to STL/OBJ in millimetres for 3D printing.

Other add-ons: use the public API in ``api`` (also importable as
``model_rail_api`` while this add-on is enabled).  See README.md in the repository.
"""

bl_info = {
    "name": "Model Rail Generator",
    "author": "John (singerlinks.com)",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > Rail",
    "description": "Generate and export straight or curved model railroad rail (code 40-332)",
    "category": "Add Mesh",
}

import sys

if "bpy" in locals():                      # support "Reload Scripts"
    import importlib
    from . import profile, geometry, presets, exporters, api, ui
    for _m in (profile, geometry, presets, exporters, api, ui):
        importlib.reload(_m)
else:
    from . import profile, geometry, presets, exporters, api   # noqa: F401
    try:
        import bpy                          # noqa: F401
        from . import ui
    except ImportError:                     # imported outside Blender (tests / tools)
        ui = None

API_ALIAS = "model_rail_api"


def register():
    ui.register()
    sys.modules[API_ALIAS] = api


def unregister():
    if sys.modules.get(API_ALIAS) is api:
        del sys.modules[API_ALIAS]
    ui.unregister()
