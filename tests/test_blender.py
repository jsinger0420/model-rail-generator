import os, sys, tempfile, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["MODEL_RAIL_PRESETS"] = os.path.join(tempfile.mkdtemp(), "p.json")
import bpy
import model_rail_generator as addon
addon.register()
import model_rail_api as rail
print("API", rail.API_VERSION)
sc = bpy.context.scene
s = sc.model_rail
print("default preset:", s.preset, round(s.height,3))
s.preset = "Code 83"; assert abs(s.height - 2.1082) < 1e-6

# UI operators
s.path_mode = "ARC"; s.path_units = "INCH"; s.radius = 18; s.angle = 22.5
assert bpy.ops.model_rail.generate() == {'FINISHED'}
o = bpy.context.active_object
lo = min(v.co.x for v in o.data.vertices); print("arc obj", o.name, "min x (m)", round(lo,4), "~ -18in*(1-cos22.5)=", round(-0.4572*(1-math.cos(math.radians(22.5))),4))
p = rail.get_rail_params(o); assert p["path"]["radius"] == 457.2
s.preset_name = "My Code 83"; s.head_width = 1.0
assert bpy.ops.model_rail.save_preset('EXEC_DEFAULT') == {'FINISHED'}
assert s.preset == "My Code 83" and "My Code 83" in rail.list_user_presets()
s.path_mode = "STRAIGHT"; s.path_units = "MM"; print("len after unit switch (mm)", round(s.length,3))
s.length = 150
assert bpy.ops.model_rail.rebuild() == {'FINISHED'}
assert rail.get_rail_params(o)["path"]["kind"] == "STRAIGHT"
s.code_input = 70; bpy.ops.model_rail.from_code(); assert abs(s.height-1.778)<1e-6

tmp = tempfile.mkdtemp()
out = os.path.join(tmp, "x.stl")
assert bpy.ops.model_rail.export('EXEC_DEFAULT', filepath=out, format="STL") == {'FINISHED'}
md = rail.object_to_mesh_data(o)
print("exported", os.path.getsize(out), "bytes; manifold", md.is_manifold(), "vol mm3", round(md.volume(),2),
      "expected", round(rail.get_preset("My Code 83").cross_section_area()*150,2))
lo, hi = md.bounds(); print("bounds mm", [round(v,2) for v in lo], [round(v,2) for v in hi])

# API: two-rail HO track on curve object
bpy.ops.curve.primitive_bezier_circle_add(radius=0.3)
c = bpy.context.active_object
for side in (-1, 1):
    r = rail.create_rail_along_curve(c, "Code 100", lateral_offset=side*16.5/2 + side*0)  # HO gauge 16.5mm
    md = rail.object_to_mesh_data(r); print("curve rail", r.name, "manifold", md.is_manifold(), "faces", len(md.faces))
# API: track pieces via ARC
objs = [rail.create_rail_object("Code 83", {"kind":"ARC","radius":457.2,"angle":30}, lateral_offset=off) for off in (-8.25, 8.25)]
rail.export_rail(objs, os.path.join(tmp,"track.obj"))
print("track export ok", os.path.getsize(os.path.join(tmp,"track.obj")))
# mm-unit scene
sc.unit_settings.scale_length = 0.001
r = rail.create_rail_object(100, {"kind":"STRAIGHT","length":10})
print("mm scene height BU", round(max(v.co.z for v in r.data.vertices),4))
s.preset = "My Code 83"; assert bpy.ops.model_rail.delete_preset('EXEC_DEFAULT') == {'FINISHED'}
addon.unregister(); assert "model_rail_api" not in sys.modules
print("ALL BLENDER TESTS PASSED")
