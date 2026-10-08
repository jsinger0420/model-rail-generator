"""Simulates clicking Generate (modal wait-cursor path) and draws the panels
with a recording layout. Run: python tests/test_ui_flow.py  (needs bpy)."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["MODEL_RAIL_PRESETS"] = os.path.join(tempfile.mkdtemp(), "p.json")
import bpy
import model_rail_generator as addon
addon.register()
from model_rail_generator import ui

log = []

class Rec:
    """Records layout calls; every method returns another recorder."""
    def __init__(self, name="layout"): self.__dict__["_n"] = name
    def __getattr__(self, a):
        def f(*args, **kw):
            log.append((a, args, kw)); return Rec(a)
        return f
    def __setattr__(self, a, v): log.append(("set", a, v))

class Win:
    def cursor_modal_set(self, c): log.append(("cursor", c))
    def cursor_modal_restore(self): log.append(("cursor", "restore"))
class WS:
    def status_text_set(self, t): log.append(("status", t))
class WM:
    def event_timer_add(self, t, window=None): log.append(("timer_add",)); return "T"
    def event_timer_remove(self, t): log.append(("timer_remove",))
    def modal_handler_add(self, op): log.append(("modal_add",))

class Ctx:
    window, workspace, window_manager, screen = Win(), WS(), WM(), None
    def __getattr__(self, a): return getattr(bpy.context, a)

class Ev:
    def __init__(self, t): self.type = t

class FakeOp:
    _timer = None
    def report(self, lvl, msg): log.append(("report", msg))
    _run = ui.MODELRAIL_OT_generate._run

def draw(panel):
    log.clear(); obj = type("P", (), {"layout": Rec()})()
    panel.draw(obj, bpy.context)
    return [(a, args, kw) for a, args, kw in log if a in ("operator", "label", "prop")]

ctx, op = Ctx(), FakeOp()
n_before = len(bpy.data.objects)

# click Generate
log.clear()
assert ui.MODELRAIL_OT_generate.invoke(op, ctx, None) == {'RUNNING_MODAL'}
assert ("cursor", "WAIT") in log and ("status", "Generating rail, please wait...") in log
assert ui.is_busy()
# a second click while busy is refused
assert ui.MODELRAIL_OT_generate.invoke(op, ctx, None) == {'CANCELLED'}
# panel while busy: wait message instead of the Generate button
calls = draw(ui.MODELRAIL_PT_main)
first = calls[0]
assert first[0] == "label" and "please wait" in first[2]["text"], first
assert not any(a == "operator" and args[0] == "model_rail.generate" for a, args, kw in calls)
# user clicks / keys while busy are swallowed, nothing built yet
for t in ("LEFTMOUSE", "A", "MOUSEMOVE"):
    assert ui.MODELRAIL_OT_generate.modal(op, ctx, Ev(t)) == {'RUNNING_MODAL'}
assert len(bpy.data.objects) == n_before
# timer tick: build, restore cursor, clear status
log.clear()
assert ui.MODELRAIL_OT_generate.modal(op, ctx, Ev("TIMER")) == {'FINISHED'}
assert ("cursor", "restore") in log and ("status", None) in log and not ui.is_busy()
assert len(bpy.data.objects) == n_before + 1
print("modal flow ok:", bpy.context.scene.model_rail.last_report)

# idle panel: Generate first, then Update, then Export
calls = draw(ui.MODELRAIL_PT_main)
ops = [args[0] for a, args, kw in calls if a == "operator"]
assert ops[:3] == ["model_rail.generate", "model_rail.rebuild", "model_rail.export"], ops
print("main panel order:", ops, "| labels:", [kw.get("text") for a, args, kw in calls if a == "label"])
draw(ui.MODELRAIL_PT_profile); draw(ui.MODELRAIL_PT_shape)

# invalid profile: generate disabled message shown
s = bpy.context.scene.model_rail
s.head_depth = 5.0
calls = draw(ui.MODELRAIL_PT_main)
assert any(a == "label" and "Fix the profile" in kw.get("text", "") for a, args, kw in calls)
assert ("set", "enabled", False) in log
addon.unregister()
print("ALL UI FLOW TESTS PASSED")
