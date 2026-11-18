"""S4b: import a DXF into FreeCAD (console) and report layers / objects / texts / errors.

Run: set SPIKE_DXF=<file> (default out\\spike\\s4_layers.dxf) then
     powershell -NoProfile -File scripts\\spike\\run_spike.ps1 -Name s4b_freecad_import -Console
"""
import collections
import os
import sys

sys.path.insert(0, os.environ.get("SPIKE_DIR", os.path.dirname(os.path.abspath(__file__))))
import _common as C  # noqa: E402


def main():
    C.start("s4b_freecad_import")
    import FreeCAD
    import importDXF

    path = os.environ.get("SPIKE_DXF", os.path.join(C.OUT, "s4_layers.dxf"))
    p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Draft")
    for k in ("dxftext", "dxfImportTexts"):
        p.SetBool(k, True)
    C.log("importing", path)
    doc = importDXF.open(path)
    C.log("doc:", doc is not None)
    objs = doc.Objects
    C.log("objects:", len(objs), dict(collections.Counter(o.TypeId for o in objs).most_common(8)))
    layers = [o for o in objs if getattr(o, "Proxy", None).__class__.__name__ == "Layer"]
    C.log("Draft layers:", len(layers), [o.Label for o in layers])
    texts = [o for o in objs if "Text" in o.TypeId or getattr(o, "Text", None)]
    C.log("text-like objects:", len(texts))
    for o in texts[:6]:
        C.log("  ", o.Label, getattr(o, "Text", None))
    return True


C.run(main)
