"""Blender UI: scene properties, operators and the sidebar panel.

Everything here goes through ``api`` so the UI and other add-ons always
behave identically.
"""

from __future__ import annotations

import math
import os

import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)
from bpy.types import Operator, Panel, PropertyGroup

from . import api
from .profile import RailProfile, profile_from_code

INCH = 25.4
PROFILE_FIELDS = ("height", "head_width", "head_depth", "web_thickness", "base_width",
                  "base_thickness", "base_edge_thickness", "head_corner_radius")

_preset_items_cache: list = []   # Blender requires dynamic enum items to stay referenced


def _preset_items(self, context):
    global _preset_items_cache
    items = []
    for i, n in enumerate(api.list_presets()):
        p = api.get_preset(n)
        tag = "" if api.is_builtin_preset(n) else " (user)"
        items.append((n, n + tag, f"{p.description}  [{p.height:.3f} mm high]", i))
    _preset_items_cache = items or [("NONE", "No presets", "", 0)]
    return _preset_items_cache


def _on_preset(self, context):
    try:
        p = api.get_preset(self.preset)
    except KeyError:
        return
    self.load_profile(p)


def _on_units(self, context):
    f = (1 / INCH) if self.path_units == "INCH" else INCH
    if self.path_units == self.get("_last_units", "MM"):
        return
    self.length *= f
    self.radius *= f
    self.lateral_offset *= f
    self["_last_units"] = self.path_units


def _poll_curve(self, obj):
    return obj.type == "CURVE"


_DEF = profile_from_code(100)
_DEFAULT_PRESET_INDEX = api.list_builtin_presets().index(_DEF.name)


def _dim(name, desc, default):
    return FloatProperty(name=name, description=desc + " (mm, actual model size)",
                         default=default, min=0.0, soft_max=50.0, precision=3, step=1)


class MODELRAIL_PG_settings(PropertyGroup):
    # ---------------------------------------------------------- profile
    preset: EnumProperty(name="Preset", items=_preset_items, update=_on_preset,
                         default=_DEFAULT_PRESET_INDEX)
    preset_name: StringProperty(name="Name", default="Code 100",
                                description="Name used when saving a preset")
    description: StringProperty(name="Description", default="")

    height: _dim("Height", "Overall rail height; rail code = height in 1/1000 inch", _DEF.height)
    head_width: _dim("Head Width", "Width of the railhead", _DEF.head_width)
    head_depth: _dim("Head Depth", "Vertical depth of the railhead", _DEF.head_depth)
    web_thickness: _dim("Web", "Thickness of the web", _DEF.web_thickness)
    base_width: _dim("Base Width", "Width of the foot / base", _DEF.base_width)
    base_thickness: _dim("Base (at web)", "Base thickness where it meets the web", _DEF.base_thickness)
    base_edge_thickness: _dim("Base (at edge)", "Base thickness at the flange tips", _DEF.base_edge_thickness)
    head_corner_radius: _dim("Head Radius", "Radius of the railhead top corners", _DEF.head_corner_radius)
    corner_segments: IntProperty(name="Radius Segments", default=_DEF.corner_segments, min=1, max=16)
    code_input: FloatProperty(name="Code", default=100.0, min=1.0, soft_max=500.0, precision=0,
                              description="Rail code (height in thousandths of an inch)")

    # ------------------------------------------------------------- path
    path_mode: EnumProperty(name="Shape", items=[
        ("STRAIGHT", "Straight", "Straight length of rail", "IPO_LINEAR", 0),
        ("ARC", "Curved", "Circular curve", "SPHERECURVE", 1),
        ("CURVE_OBJECT", "Along Curve", "Follow a curve object in the scene", "CURVE_DATA", 2),
    ], default="STRAIGHT")
    path_units: EnumProperty(name="Units", items=[("MM", "mm", ""), ("INCH", "in", "")],
                             default="MM", update=_on_units,
                             description="Units for length, radius and offset")
    length: FloatProperty(name="Length", default=200.0, min=0.001, precision=3)
    radius: FloatProperty(name="Radius", default=457.2, min=0.001, precision=3,
                          description="Radius to the rail centreline")
    angle: FloatProperty(name="Angle", default=30.0, min=0.01, max=360.0, precision=2,
                         description="Arc angle in degrees")
    direction: EnumProperty(name="Direction", items=[("LEFT", "Left", ""), ("RIGHT", "Right", "")])
    max_segment_angle: FloatProperty(name="Max Segment Angle", default=1.0, min=0.05, max=15.0,
                                     description="Smaller = smoother curve, more polygons")
    curve_object: PointerProperty(name="Curve", type=bpy.types.Object, poll=_poll_curve)
    lateral_offset: FloatProperty(name="Offset", default=0.0, precision=3,
                                  description="Shift the rail right (+) or left (-) of the path")
    cant: FloatProperty(name="Cant", default=0.0, min=-10.0, max=10.0, precision=2,
                        description="Rail tilt in degrees (+ leans head right)")
    cap_ends: BoolProperty(name="Cap Ends", default=True,
                           description="Close the rail ends (required for a printable solid)")

    # ----------------------------------------------------------- status
    last_report: StringProperty(name="Last Result", default="",
                                description="Result of the last Generate / Update / Export")

    # ----------------------------------------------------------- export
    export_format: EnumProperty(name="Format", items=[
        ("STL", "STL (binary)", "Best for 3D printing"),
        ("STL_ASCII", "STL (ASCII)", "Text STL"),
        ("OBJ", "OBJ", "Wavefront OBJ"),
    ])

    # ---------------------------------------------------------- helpers
    def load_profile(self, p: RailProfile):
        for f in PROFILE_FIELDS:
            setattr(self, f, getattr(p, f))
        self.corner_segments = p.corner_segments
        self.description = p.description
        self.preset_name = p.name
        self.code_input = round(p.code)

    def to_profile(self) -> RailProfile:
        kw = {f: getattr(self, f) for f in PROFILE_FIELDS}
        return RailProfile(name=self.preset_name.strip() or "Custom",
                           corner_segments=self.corner_segments,
                           description=self.description, **kw)

    def to_mm(self, v: float) -> float:
        return v * INCH if self.path_units == "INCH" else v

    def path_spec(self) -> dict:
        if self.path_mode == "ARC":
            return {"kind": "ARC", "radius": self.to_mm(self.radius), "angle": self.angle,
                    "direction": self.direction, "max_segment_angle": self.max_segment_angle}
        return {"kind": "STRAIGHT", "length": self.to_mm(self.length)}


def _settings(context) -> MODELRAIL_PG_settings:
    return context.scene.model_rail


def _check_profile(op, s):
    p = s.to_profile()
    errs = p.validate()
    if errs:
        op.report({'ERROR'}, "Invalid profile: " + "; ".join(errs))
        return None
    return p


# ================================================================ operators
_busy = False


def is_busy() -> bool:
    """True while a rail is being generated (the panel shows a wait message)."""
    return _busy


def _redraw(context):
    screen = context.screen
    if screen:
        for area in screen.areas:
            area.tag_redraw()


class MODELRAIL_OT_generate(Operator):
    """Create a rail object at the 3D cursor from the current profile and shape"""

    bl_idname = "model_rail.generate"
    bl_label = "Generate Rail"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None

    def _run(self, context):
        s = _settings(context)
        p = _check_profile(self, s)
        if p is None:
            s.last_report = "Invalid profile - see the Profile panel"
            return {'CANCELLED'}
        try:
            if s.path_mode == "CURVE_OBJECT":
                if not s.curve_object:
                    self.report({'ERROR'}, "Pick a curve object")
                    s.last_report = "Pick a curve object in the Shape panel"
                    return {'CANCELLED'}
                obj = api.create_rail_along_curve(s.curve_object, p,
                                                  lateral_offset=s.to_mm(s.lateral_offset),
                                                  cant_deg=s.cant, cap_ends=s.cap_ends)
            else:
                obj = api.create_rail_object(p, s.path_spec(),
                                             location=context.scene.cursor.location.copy(),
                                             lateral_offset=s.to_mm(s.lateral_offset),
                                             cant_deg=s.cant, cap_ends=s.cap_ends)
        except (ValueError, TypeError) as ex:
            self.report({'ERROR'}, str(ex))
            s.last_report = str(ex).splitlines()[0]
            return {'CANCELLED'}
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        s.last_report = f"Created '{obj.name}' ({len(obj.data.polygons)} faces)"
        self.report({'INFO'}, s.last_report)
        return {'FINISHED'}

    def execute(self, context):
        # Scripts and the redo panel: build straight away.
        return self._run(context)

    def invoke(self, context, event):
        """Show the wait message and busy cursor first, then build on the next timer tick.

        Blender doesn't redraw while an operator runs, so the build waits one
        tick to let the panel show "please wait".
        """
        global _busy
        if _busy:
            return {'CANCELLED'}
        _busy = True
        wm = context.window_manager
        context.window.cursor_modal_set('WAIT')
        if context.workspace:
            context.workspace.status_text_set("Generating rail, please wait...")
        _redraw(context)
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        global _busy
        if event.type != 'TIMER':
            return {'RUNNING_MODAL'}  # ignore clicks and keys until the build is done
        context.window_manager.event_timer_remove(self._timer)
        try:
            return self._run(context)
        finally:
            context.window.cursor_modal_restore()
            if context.workspace:
                context.workspace.status_text_set(None)
            _busy = False
            _redraw(context)


class MODELRAIL_OT_rebuild(Operator):
    bl_idname = "model_rail.rebuild"
    bl_label = "Update Selected Rails"
    bl_description = "Regenerate selected rail objects with the current profile and shape settings"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(api.is_rail_object(o) for o in context.selected_objects)

    def execute(self, context):
        s = _settings(context)
        p = _check_profile(self, s)
        if p is None:
            return {'CANCELLED'}
        n = 0
        for o in context.selected_objects:
            if not api.is_rail_object(o):
                continue
            params = api.get_rail_params(o)
            path = params["path"] if (s.path_mode == "CURVE_OBJECT" or "source_curve" in params) \
                else s.path_spec()
            api.rebuild_rail_object(o, profile=p, path=path,
                                    lateral_offset=s.to_mm(s.lateral_offset),
                                    cant_deg=s.cant, cap_ends=s.cap_ends)
            n += 1
        s.last_report = f"Updated {n} rail(s)"
        self.report({'INFO'}, s.last_report)
        return {'FINISHED'}


class MODELRAIL_OT_from_code(Operator):
    bl_idname = "model_rail.from_code"
    bl_label = "Fill From Code"
    bl_description = "Fill all dimensions with typical proportions for the entered rail code"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = _settings(context)
        s.load_profile(profile_from_code(s.code_input, description="Custom"))
        return {'FINISHED'}


class MODELRAIL_OT_save_preset(Operator):
    bl_idname = "model_rail.save_preset"
    bl_label = "Save Preset"
    bl_description = "Save the current dimensions as a user preset"

    overwrite: BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        name = _settings(context).preset_name.strip()
        if name in api.list_user_presets():
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context):
        s = _settings(context)
        p = _check_profile(self, s)
        if p is None:
            return {'CANCELLED'}
        if api.is_builtin_preset(p.name):
            self.report({'ERROR'}, f"'{p.name}' is built in; enter a new name to save")
            return {'CANCELLED'}
        try:
            api.save_preset(p, overwrite=True)
        except api.PresetError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        s.preset = p.name
        self.report({'INFO'}, f"Saved preset '{p.name}'")
        return {'FINISHED'}


class MODELRAIL_OT_delete_preset(Operator):
    bl_idname = "model_rail.delete_preset"
    bl_label = "Delete Preset"
    bl_description = "Delete the selected user preset"

    @classmethod
    def poll(cls, context):
        return not api.is_builtin_preset(_settings(context).preset)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        s = _settings(context)
        name = s.preset
        try:
            api.delete_preset(name)
        except (api.PresetError, KeyError) as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        s.preset = api.list_presets()[0]
        self.report({'INFO'}, f"Deleted preset '{name}'")
        return {'FINISHED'}


class MODELRAIL_OT_export(Operator):
    bl_idname = "model_rail.export"
    bl_label = "Export Rail"
    bl_description = ("Export selected objects (or, if none are selected, a rail built from the "
                      "current settings) to STL/OBJ in millimetres")

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default="*.stl;*.obj", options={'HIDDEN'})
    format: EnumProperty(name="Format", items=[
        ("STL", "STL (binary)", ""), ("STL_ASCII", "STL (ASCII)", ""), ("OBJ", "OBJ", "")])
    selected_only: BoolProperty(name="Selected Objects", default=True,
                                description="Export selected meshes; otherwise build from settings")

    def invoke(self, context, event):
        s = _settings(context)
        self.format = s.export_format
        base = bpy.path.clean_name(s.preset_name or "rail")
        self.filepath = bpy.path.ensure_ext(base, ".obj" if self.format == "OBJ" else ".stl")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        s = _settings(context)
        ext = ".obj" if self.format == "OBJ" else ".stl"
        path = bpy.path.ensure_ext(bpy.path.abspath(self.filepath), ext)
        objs = [o for o in context.selected_objects if o.type == 'MESH'] if self.selected_only else []
        try:
            if objs:
                api.export_rail(objs, path, self.format)
                what = f"{len(objs)} object(s)"
            else:
                p = _check_profile(self, s)
                if p is None:
                    return {'CANCELLED'}
                if s.path_mode == "CURVE_OBJECT":
                    self.report({'ERROR'}, "Generate the rail first, then export it selected")
                    return {'CANCELLED'}
                md = api.generate_rail_mesh(p, s.path_spec(), s.to_mm(s.lateral_offset),
                                            s.cant, s.cap_ends)
                api.export_rail(md, path, self.format, p.name)
                what = "rail from current settings"
        except (OSError, ValueError) as ex:
            self.report({'ERROR'}, f"Export failed: {ex}")
            return {'CANCELLED'}
        s.export_format = self.format
        s.last_report = f"Exported {what} to {os.path.basename(path)}"
        self.report({'INFO'}, f"Exported {what} to {path}")
        return {'FINISHED'}


# =================================================================== panels
class _Panel:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Rail"


class MODELRAIL_PT_main(_Panel, Panel):
    """Top of the Rail tab: Generate, Update, Export and the last result."""

    bl_label = "Model Rail"
    bl_idname = "MODELRAIL_PT_main"

    def draw(self, context):
        s = _settings(context)
        col = self.layout.column()
        p = s.to_profile()
        errs = p.validate()

        row = col.row(align=True)
        row.scale_y = 1.4
        if is_busy():
            row.alert = True
            row.label(text="Generating rail, please wait...", icon='SORTTIME')
        else:
            row.enabled = not errs
            row.operator(MODELRAIL_OT_generate.bl_idname, icon='ADD')
        col.operator(MODELRAIL_OT_rebuild.bl_idname, icon='FILE_REFRESH')

        row = col.row(align=True)
        row.operator(MODELRAIL_OT_export.bl_idname, icon='EXPORT')
        row.prop(s, "export_format", text="")

        if errs:
            box = col.box()
            box.alert = True
            box.label(text="Fix the profile to generate:", icon='ERROR')
            for e in errs[:3]:
                box.label(text=e)
        elif s.last_report:
            col.label(text=s.last_report, icon='INFO')

        box = col.box()
        name = p.name if p.name.lower().startswith("code") else f"{p.name} (code {p.code:g})"
        box.label(text=f"{name}, {p.height:.3f} mm high", icon='MOD_SOLIDIFY')
        if s.path_mode == "STRAIGHT":
            box.label(text=f"Straight, {s.to_mm(s.length):.1f} mm long")
        elif s.path_mode == "ARC":
            arc = math.radians(s.angle) * s.to_mm(s.radius)
            box.label(text=f"{s.direction.title()} curve, R {s.to_mm(s.radius):.1f} mm, "
                           f"{s.angle:g}° ({arc:.1f} mm)")
        else:
            box.label(text=f"Along {s.curve_object.name}" if s.curve_object
                      else "Along curve: none picked")


class MODELRAIL_PT_profile(_Panel, Panel):
    bl_label = "Rail Profile"
    bl_parent_id = "MODELRAIL_PT_main"

    def draw(self, context):
        s = _settings(context)
        col = self.layout.column()
        row = col.row(align=True)
        row.prop(s, "preset", text="")
        row.operator(MODELRAIL_OT_delete_preset.bl_idname, text="", icon='TRASH')
        p = s.to_profile()
        col.label(text=f"Code {p.code:g}   ({p.height:.3f} mm / {p.height / INCH:.4f} in)")
        sub = col.column(align=True)
        for f in PROFILE_FIELDS:
            sub.prop(s, f)
        sub.prop(s, "corner_segments")
        for e in p.validate()[:3]:
            col.label(text=e, icon='ERROR')

        row = col.row(align=True)
        row.prop(s, "code_input")
        row.operator(MODELRAIL_OT_from_code.bl_idname, text="Fill From Code")

        sub = col.column(align=True)
        sub.prop(s, "preset_name")
        sub.prop(s, "description", text="Notes")
        sub.operator(MODELRAIL_OT_save_preset.bl_idname, icon='FILE_TICK')


class MODELRAIL_PT_shape(_Panel, Panel):
    bl_label = "Shape"
    bl_parent_id = "MODELRAIL_PT_main"

    def draw(self, context):
        s = _settings(context)
        box = self.layout.column()
        box.row().prop(s, "path_mode", expand=True)
        col = box.column(align=True)
        if s.path_mode != "CURVE_OBJECT":
            col.row().prop(s, "path_units", expand=True)
        u = "in" if s.path_units == "INCH" else "mm"
        if s.path_mode == "STRAIGHT":
            col.prop(s, "length", text=f"Length ({u})")
        elif s.path_mode == "ARC":
            col.prop(s, "radius", text=f"Radius ({u})")
            col.prop(s, "angle", text="Angle (°)")
            col.row().prop(s, "direction", expand=True)
            col.prop(s, "max_segment_angle")
            arc = math.radians(s.angle) * s.to_mm(s.radius)
            col.label(text=f"Arc length {arc:.1f} mm")
        else:
            col.prop(s, "curve_object")
        col = box.column(align=True)
        col.prop(s, "lateral_offset", text=f"Offset ({u})")
        col.prop(s, "cant", text="Cant (°)")
        col.prop(s, "cap_ends")


classes = (
    MODELRAIL_PG_settings,
    MODELRAIL_OT_generate,
    MODELRAIL_OT_rebuild,
    MODELRAIL_OT_from_code,
    MODELRAIL_OT_save_preset,
    MODELRAIL_OT_delete_preset,
    MODELRAIL_OT_export,
    MODELRAIL_PT_main,
    MODELRAIL_PT_profile,
    MODELRAIL_PT_shape,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.model_rail = PointerProperty(type=MODELRAIL_PG_settings)


def unregister():
    del bpy.types.Scene.model_rail
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
