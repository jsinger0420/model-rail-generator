"""Test profiles, presets, geometry and export without Blender.

Run: python tests/test_core.py
"""

import math, os, sys, tempfile, struct
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from model_rail_generator import api
from model_rail_generator.geometry import triangulate_polygon
from model_rail_generator.profile import polygon_area

def check(md, label):
    """Assert ``md`` is a closed solid with outward-facing normals."""
    assert md.is_manifold(), label + " not manifold"
    assert md.volume() > 0, label + " inverted"

for n in api.list_presets():
    p = api.get_preset(n)
    assert p.is_valid(), (n, p.validate())
    o = p.outline()
    assert polygon_area(o) > 0
    tris = triangulate_polygon(o)
    ta = sum(abs(polygon_area([o[a],o[b],o[c]])) for a,b,c in tris)
    assert abs(ta - polygon_area(o)) < 1e-9, (n, ta, polygon_area(o))
    print(f"{n:10s} h={p.height:.3f} head={p.head_width:.3f} base={p.base_width:.3f} area={p.cross_section_area():.4f}mm2")

p = api.get_preset("Code 100")
assert abs(p.height - 2.54) < 1e-9 and p.code == 100
assert abs(api.get_preset("Code 83").height - 2.1082) < 1e-9

# straight: volume = area * length
md = api.generate_rail_mesh("Code 100", {"kind":"STRAIGHT","length":100})
check(md, "straight")
assert abs(md.volume() - p.cross_section_area()*100) < 1e-6
# arc: Pappus — volume = area * angle * radius of centroid; centroid x near 0
for d in ("LEFT","RIGHT"):
    md = api.generate_rail_mesh("Code 83", {"kind":"ARC","radius":457.2,"angle":90,"direction":d,"max_segment_angle":0.5})
    check(md, "arc "+d)
    a = api.get_preset("Code 83").cross_section_area()
    exp = a*math.pi/2*457.2
    assert abs(md.volume()-exp)/exp < 1e-3, (md.volume(), exp)
    lo, hi = md.bounds()
    end = (-457.2 if d=="LEFT" else 457.2)
    print(d, "bounds", [round(v,2) for v in lo], [round(v,2) for v in hi])
# offset arc: rail moves to radius+offset on LEFT curve
md = api.generate_rail_mesh(84, {"kind":"ARC","radius":500,"angle":45}, lateral_offset=8.25)
check(md,"offset arc")
# full circle closed (no caps)
md = api.generate_rail_mesh("Code 55", {"kind":"ARC","radius":200,"angle":360})
check(md,"circle")
# polyline + cant
md = api.generate_rail_mesh("Code 70", {"kind":"POLYLINE","points":[(0,0,0),(0,50,0),(30,90,2),(80,100,4)]}, cant_deg=1.4)
check(md,"polyline")
# no-radius profile
p0 = p.copy(name="sharp", head_corner_radius=0)
check(api.generate_rail_mesh(p0, {"kind":"STRAIGHT","length":10}), "sharp")
# validation
bad = p.copy(head_depth=2.0, base_thickness=1.0)
assert bad.validate()
try:
    api.generate_rail_mesh(bad, {"kind":"STRAIGHT","length":10}); raise SystemExit("should fail")
except ValueError as e: print("validation ok:", e)

# presets
tmp = tempfile.mkdtemp()
api.set_preset_file(os.path.join(tmp, "p.json"))
my = p.copy(name="Peco Code 100 measured", head_width=1.1, description="calipers")
api.save_preset(my)
api.set_preset_file(os.path.join(tmp, "p.json"))  # force reload from disk
assert api.get_preset("Peco Code 100 measured").head_width == 1.1
assert "Peco Code 100 measured" in api.list_user_presets()
try: api.save_preset(p); raise SystemExit("builtin overwrite allowed")
except api.PresetError: pass
try: api.delete_preset("Code 83"); raise SystemExit("builtin delete")
except api.PresetError: pass
api.export_presets(os.path.join(tmp,"share.json"))
api.delete_preset("Peco Code 100 measured")
assert api.import_presets(os.path.join(tmp,"share.json")) == ["Peco Code 100 measured"]

# export
md = api.generate_rail_mesh("Code 83", {"kind":"ARC","radius":300,"angle":30})
f = api.export_rail(md, os.path.join(tmp,"r.stl"))
data = open(f,"rb").read()
n = struct.unpack("<I", data[80:84])[0]
assert len(data) == 84 + 50*n == 84+50*len(md.triangles())
api.export_rail(md, os.path.join(tmp,"r.obj"))
api.export_rail(md, os.path.join(tmp,"a.stl"), "STL_ASCII")
print("STL tris", n, "OK — all core tests passed")
